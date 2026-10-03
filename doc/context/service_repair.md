# Repair service station log

SERVICE__CALLS_BOUND=1 - покажет вызовы привязанного сервиса, в том числе GetDamageReports и RepairItems; 
SERVICE__MESSAGE=1 - поможет увидеть вызов, переданный вместе с привязкой; 
ATTRIBUTE__CHANGE=1 - покажет изменения атрибутов корабля. 
COLLECT__PACKET_DUMP=1 

(src/eve-server/Client.cpp:2676-2695, src/eve-server/services/BoundService.h:129-145, src/eve-server/inventory/AttributeMap.cpp:260-280).