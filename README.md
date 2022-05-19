# Rucio-SENSE Interoperation Prototype Simulation

## Southbound
Contains components that allow high-level components to communicate with low-level components
- Burro: stand-in for Rucio
```
./bin/burro
```
- [DMM](https://github.com/jkguiang/rucio-sense-dmm)

## Northbound
Contains components that allow low-level components to communicate with high-level components
- PSNet: stand-in for ESNet+FTS
```
./bin/psnet
```
- NONSENSE: stand-in for SENSE
```
./bin/nonsense
```
