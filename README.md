# DEFA + iHomeManager Load Balancer

Custom Home Assistant integration to load-balance a DEFA EV charger using Sungrow iHomeManager (Modbus TCP).

## Install (HACS - Custom repository)
1. HACS → Integrations → ⋮ → Custom repositories
2. Add this repo URL as **Integration**
3. Install and restart Home Assistant

## Setup
Settings → Devices & services → Add integration → "DEFA + iHomeManager Load Balancer"

Defaults:
- iHomeManager: 192.168.1.42
- DEFA: 192.168.1.56
- Eco grid limit per phase: configurable (default 2A)

## Notes
- DEFA Modbus must be enabled and allows only one Modbus master at a time.
- iHomeManager port allows only one TCP connection.
