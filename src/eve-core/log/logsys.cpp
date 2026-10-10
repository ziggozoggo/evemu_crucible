/*
 *    ------------------------------------------------------------------------------------
 *    LICENSE:
 *    ------------------------------------------------------------------------------------
 *    This file is part of EVEmu: EVE Online Server Emulator
 *    Copyright 2006 - 2021 The EVEmu Team
 *    For the latest information visit https://evemu.dev
 *    ------------------------------------------------------------------------------------
 *    This program is free software; you can redistribute it and/or modify it under
 *    the terms of the GNU Lesser General Public License as published by the Free Software
 *    Foundation; either version 2 of the License, or (at your option) any later
 *    version.
 *
 *    This program is distributed in the hope that it will be useful, but WITHOUT
 *    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
 *    FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more details.
 *
 *    You should have received a copy of the GNU Lesser General Public License along with
 *    this program; if not, write to the Free Software Foundation, Inc., 59 Temple
 *    Place - Suite 330, Boston, MA 02111-1307, USA, or go to
 *    http://www.gnu.org/copyleft/lesser.txt.
 *    ------------------------------------------------------------------------------------
 *    Author:     Zhur
 */

#include "eve-core.h"

#include "log/logsys.h"
#include "utils/utils_hex.h"
#include "threading/Mutex.h"

#include <chrono>

Mutex mLogSys;

FILE *logsys_log_file(nullptr);

#define LOG_CATEGORY(category) #category ,
const char *log_category_names[NUMBER_OF_LOG_CATEGORIES] = {
    #include "log/logtypes.h"
};

//this array is private to this file, only a const version of it is exposed
#define LOG_TYPE(category, type, enabled, str) { enabled, LOG_ ##category, #category "__" #type, str },
static LogTypeStatus real_log_type_info[NUMBER_OF_LOG_TYPES+1] ={
    #include "log/logtypes.h"
    #include "utils/Lock.h"     // why is this here?
    { false, NUMBER_OF_LOG_CATEGORIES, "BAD TYPE", "Bad Name" } /* dummy trailing record */
};

const LogTypeStatus *log_type_info = real_log_type_info;

void log_format_timestamp(char* buffer, size_t size) {
    const auto now = std::chrono::system_clock::now();
    const auto whole_second = std::chrono::floor<std::chrono::seconds>(now);
    const time_t seconds = std::chrono::system_clock::to_time_t(whole_second);
    const auto micros = std::chrono::duration_cast<std::chrono::microseconds>(now - whole_second).count();

    tm local_time;
    if (localtime_r(&seconds, &local_time) == nullptr) {
        snprintf(buffer, size, "??:??:??.%06lld", static_cast<long long>(micros));
        return;
    }

    snprintf(buffer, size, "%02d:%02d:%02d.%06lld",
             local_time.tm_hour, local_time.tm_min, local_time.tm_sec, static_cast<long long>(micros));
}

void log_hex(LogType type, const void *data, unsigned long length, unsigned char padding) {
    char buffer[1030];
    uint32 offset;
    for(offset=0;offset<length;offset+=16) {
        build_hex_line((const uint8 *)data,length,offset,buffer,padding);
        log_message(type, "%s", buffer);    //%s is to prevent % escapes in the ascii
    }
}

void log_phex(LogType type, const void *data, unsigned long length, unsigned char padding) {
    if (length <= 1024)
        log_hex(type, data, length, padding);
    else {
        char buffer[1030];
        log_hex(type, data, 1024-32, padding);
        log_message(type, " ... truncated ...");
        build_hex_line((const uint8 *)data,length,length-16,buffer,padding);
        log_message(type, "%s", buffer);
    }
}

void log_message(LogType type, const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    log_messageVA(type, 0, fmt, args);
    va_end(args);
}

void log_messageVA(LogType type, const char *fmt, va_list args) {

    log_messageVA(type, 0, fmt, args);
}

extern void log_messageVA( LogType type, uint32 iden, const char *fmt, va_list args )
{
    char timestamp[16];
    log_format_timestamp(timestamp, sizeof(timestamp));

    va_list args_copy;
    va_copy(args_copy, args);
    const int message_size = vsnprintf(nullptr, 0, fmt, args_copy);
    va_end(args_copy);
    if (message_size < 0)
        return;

    std::vector<char> message(static_cast<size_t>(message_size) + 1);
    vsnprintf(message.data(), message.size(), fmt, args);

    std::string log_msg = timestamp;
    log_msg += " [";
    log_msg += log_type_info[type].display_name;
    log_msg += "] ";
    log_msg.append(iden, ' ');
    log_msg.append(message.data(), static_cast<size_t>(message_size));
    log_msg += '\n';

    MutexLock lock(mLogSys);

    fputs(log_msg.c_str(), stdout);

    //print into the logfile (if any)
    if (logsys_log_file != nullptr) {
        //fprintf(logsys_log_file, "%s\n", message.c_str());
        fputs(log_msg.c_str(), logsys_log_file);
        //keep the logfile updated
        fflush(logsys_log_file);
    }

    lock.Unlock();
}

void log_enable( LogType t )
{
    real_log_type_info[t].enabled = true;
}

void log_disable( LogType t )
{
    real_log_type_info[t].enabled = false;
}

void log_toggle( LogType t )
{
    real_log_type_info[t].enabled = !real_log_type_info[t].enabled;
}

bool log_open_logfile( const char* filename )
{
    MutexLock lock(mLogSys);
    if (logsys_log_file)
        if (!log_close_logfile())
            return false;

    logsys_log_file = fopen(filename, "w");
    return ( nullptr != logsys_log_file);
}

bool log_close_logfile()
{
    MutexLock lock(mLogSys);
    if (!logsys_log_file)
        return true;
    return ( 0 == fclose( logsys_log_file ) );
}

bool load_log_settings(const char *filename) {
    //this is a terrible algorithm, but im lazy today
    FILE *f = fopen(filename, "r");
    if (!f)
        return false;
    char linebuf[512], type_name[256], value[256];
    uint16 i(0);
    while(!feof(f)) {
        ++i;
        if (fgets(linebuf, 512, f) == nullptr)
            continue;
        if (sscanf(linebuf, "%[^=]=%[^\r\n]\n", type_name, value) != 2)
            continue;

        if (type_name[0] == '\0' || type_name[0] == '#')
            continue;

        //first make sure we understand the value
        bool enabled(false);
        if (!strcasecmp(value, "on") || !strcasecmp(value, "yes") || !strcasecmp(value, "enabled") || !strcmp(value, "1"))
            enabled = true;
        else if (!strcasecmp(value, "off") || !strcasecmp(value, "no") || !strcasecmp(value, "disabled") || !strcmp(value, "0"))
            enabled = false;
        else {
            printf("Unable to parse value '%s' from %s around line %u. Skipping.\n", value, filename, i);
            continue;
        }

        int16 r(0);
        //first see if it is a category name
        for(r = 0; r < NUMBER_OF_LOG_CATEGORIES; ++r) {
            if (!strcasecmp(log_category_names[r], type_name))
                break;
        }
        if (r != NUMBER_OF_LOG_CATEGORIES) {
            //matched a category.
            for(int16 k(0); k < NUMBER_OF_LOG_TYPES; ++k) {
                if (log_type_info[k].category != r)
                    continue;   //does not match this category.
                    if (enabled)
                        log_enable(LogType(k));
                    else
                        log_disable(LogType(k));
            }
            continue;
        }

        for(r = 0; r < NUMBER_OF_LOG_TYPES; ++r) {
            if (!strcasecmp(log_type_info[r].name, type_name))
                break;
        }
        if (r == NUMBER_OF_LOG_TYPES) {
            printf("Unable to locate log type %s from file %s around line %u. Skipping.\n", type_name, filename, i);
            continue;
        }

        //got it all figured out, do something now...
        if (enabled)
            log_enable(LogType(r));
        else
            log_disable(LogType(r));
    }
    fclose(f);
    return true;
}
