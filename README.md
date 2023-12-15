# leap-boot

These scripts are used to test deep-mind logs produced by leap, their0 decoding and validation against expected data

## Prerequsites
* Ubuntu 20.04/22.04
* Leap with cleos and keosd
* Python   
* Go 

## Validation process
### Boot
```bash
$ ./boot.sh
```
This will boot the nodes, set system contracts, run test actions, etc. Also the script will generate two log files:

* `./run/dm.log` - deep-mind log for the entire boot/test sequence,
* `./run/expected.jsonl` - log of expected actions and dbops

### Decode
```bash
$ ./decode.sh
```
This will decode deep-mind log into JSON using firehose decoder and generate `./run/dm.log.json` file

### Validate
```bash
$ ./compare.sh
```
This will extract validate expected actions/dbops from `expected.jsonl` vs deep-mind produced logs


## Known issues
Because there is no transaction guarantee, sometimes some transactions might not make it on block and compare script may error out. Try re-running the boot script in this case.