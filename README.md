# deep

These scripts are used to generate and validate deep-mind logs produced by leap boot and battlefield process

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

* `./run/deep-mind-x.x.x.dmlog` - deep-mind log for the entire boot/test sequence,
* `./run/deep-mind-x.x.x.expected.jsonl` - log of expected actions and dbops

### Decode
```bash
$ ./decode.sh
```
This will decode deep-mind log into JSON using firehose decoder and generate `./run/deep-mind-x.x.x.dmlog.json` file

### Validate
```bash
$ ./validate.sh
```
This will extract validate expected actions/dbops from `deep-mind-x.x.x.expected.jsonl` vs deep-mind produced logs


## Known issues
Because there is no transaction guarantee, sometimes some transactions might not make it on block and compare script may error out. Try re-running the boot script in this case.