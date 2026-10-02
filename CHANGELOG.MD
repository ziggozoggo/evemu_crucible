# CHANGELOG fork

Original [ChangeLog](doc/ChangeLog.md)

## 2026-10-02

Fix `649a108` @Black007Angel:
- Мгновенный Warp корабля c нулевой скоростью;
- Исправлено время экспоненты: используется elapsed time вместо 1, 3, 6, 10…; 
- Восстановлен правильный порядок состояний орбиты;
- yaw/pitch/roll не имеют потребителя; оставлены как есть;
- m_stopDistance возвращён к int32 согласно контракту `CmdWarpTo.distance`, `GetDistance()`. 

Fix `Partial Warp Desync`:
- Warp разделён на непрерывные accel/cruise/decel-фазы
- При недостатке `capacitor` (partial warp) дистанция прыжка больше не становиться `capacitor`, в свою очередь `capacitor` на становиться расстоянием -> корабль корректно прерывает Warp;
- Удалён дублирующий финальный SetBallPosition; сохраняются финальная позиция текущего тика, Stop и нулевая скорость;
- Времена фаз перенесены в WarpState как double: 
  - было uint8 m_warpAccelTime, uint8 m_warpDecelTime при дробных значениях времени разгона и торможения;
  - стало double accelTime, cruiseTime, decelTime; таким образом:
    - нет округления фаз до целых секунд;
    - нет скачка между разгоном и cruise;
    - параметры принадлежат конкретному активному warp;
    - длительность и момент начала торможения больше не смешиваются в одной переменной;

Fix `WarpTo`
- `WarpTo 10,20... desync` исправлен двойной stand-off (дистанция, на которой корабль должен остановиться до цели);
- После выхода из варпа корабль теперь сохраняет `align` на цель (удалён `SetBallVelocity(0,0,0)`, сбрасывавший клиентский heading; `WarpStop()` теперь отправляет только `CmdStop`).


m_stopDistance возвращён к int32, устраняя повреждение varargs-логов: DestinyManager.h:138,228.
https://github.com/EvEmu-Project/evemu_Crucible/pull/295