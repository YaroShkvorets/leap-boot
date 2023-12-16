#!/usr/bin/env python3

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import inspect

from log import initLogging, logAction, logDbop

args = None
logFile = None

unlockTimeout = 999999999
fastUnstakeSystem = './fast.refund/eosio.system/eosio.system.wasm'

systemAccounts = [
    'eosio.bpay',
    'eosio.msig',
    'eosio.names',
    'eosio.ram',
    'eosio.ramfee',
    'eosio.saving',
    'eosio.stake',
    'eosio.token',
    'eosio.vpay',
    'eosio.rex',
]

def stepTitle():
    calling_frame = inspect.currentframe().f_back
    calling_function = calling_frame.f_code.co_name

    total_width = 80
    title_width = len(calling_function)
    padding = (total_width - title_width) // 2
    separator = "*" * total_width

    empty_line = "*" + " " * (total_width - 2)
    title_line = f"*{' ' * padding}{calling_function}{' ' * padding}"

    print()
    print(separator)
    print(empty_line)  # Extra empty line before the title
    print(title_line)
    print(empty_line)  # Extra empty line after the title
    print(separator)
    print()


def getCleos(is_random = False):
    port = args.http_port
    # if is_random:
    #     port = random.randint(args.http_port + 1, args.http_port + numProducers)
    return args.cleos + ' --url http://127.0.0.1:%d ' % port

def jsonArg(a):
    return " '" + json.dumps(a) + "' "

def run(args):
    print('boot.py run:', args)
    logFile.write(args + '\n')
    if subprocess.call(args, shell=True):
        print('boot.py: exiting because of error')
        sys.exit(1)

def retry_with_id(args):
    while True:
        print('boot.py retry: ', args)
        
        # Run the subprocess and capture both stdout and stderr
        result = subprocess.run(args, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        combined_output = result.stdout + result.stderr
        
        
        pattern = r'transaction: (\w{64})'
        match = re.search(pattern, combined_output)
        if match:
            transaction_id = match.group(1)
            return transaction_id
        else:
            print('Error: ', result.stderr)
            print('*** Retry')
            sleep(1)
            
def retry(args):
    while True:
        print('boot.py retry: ', args)
        logFile.write(args + '\n')
        if subprocess.call(args, shell=True):
            print('*** Retry')
            sleep(1)
        else:
            break

def background(args):
    print('boot.py background:', args)
    logFile.write(args + '\n')
    return subprocess.Popen(args, shell=True)

def getOutput(args):
    print('boot.py getOutput:', args)
    logFile.write(args + '\n')
    proc = subprocess.Popen(args, shell=True, stdout=subprocess.PIPE)
    return proc.communicate()[0].decode('utf-8')

def getJsonOutput(args):
    return json.loads(getOutput(args))

def sleep(t):
    print('sleep', t, '...')
    time.sleep(t)
    print('resume')

def startWallet():
    run('rm -rf ' + os.path.abspath(args.wallet_dir))
    run('mkdir -p ' + os.path.abspath(args.wallet_dir))
    background(args.keosd + ' --unlock-timeout %d --http-server-address 127.0.0.1:6666 --http-max-response-time-ms 99999 --wallet-dir %s' % (unlockTimeout, os.path.abspath(args.wallet_dir)))
    sleep(.4)
    run(getCleos() + 'wallet create --to-console')

def importKeys():
    run(getCleos() + 'wallet import --private-key ' + args.private_key)
    keys = {}
    for a in accounts:
        key = a['pvt']
        if not key in keys:
            if len(keys) >= args.max_user_keys:
                break
            keys[key] = True
            run(getCleos() + 'wallet import --private-key ' + key)
    for i in range(firstProducer, firstProducer + numProducers):
        a = accounts[i]
        key = a['pvt']
        if not key in keys:
            keys[key] = True
            run(getCleos() + 'wallet import --private-key ' + key)

def startNode(nodeIndex, account):
    dir = args.nodes_dir + ('%02d-' % nodeIndex) + account['name'] + '/'
    run('rm -rf ' + dir)
    run('mkdir -p ' + dir)
    otherOpts = ''.join(list(map(lambda i: '    --p2p-peer-address localhost:' + str(9000 + i), range(nodeIndex))))
    if not nodeIndex: otherOpts += (
        '    --plugin eosio::trace_api_plugin --trace-no-abis'
    )
    cmd = (
        args.nodeos +
        '    --max-irreversible-block-age -1'
        # max-transaction-time must be less than block time
        # (which is defined in .../chain/include/eosio/chain/config.hpp
        # as block_interval_ms = 500)
        '    --max-transaction-time=200'
        '    --contracts-console'
        '    --genesis-json ' + os.path.abspath(args.genesis_path) +
        '    --blocks-dir ' + os.path.abspath(dir) + '/blocks'
        '    --config-dir ' + os.path.abspath(dir) +
        '    --data-dir ' + os.path.abspath(dir) +
        '    --chain-state-db-size-mb 1024'
        '    --http-server-address 0.0.0.0:' + str(args.http_port + nodeIndex) +
        '    --p2p-listen-endpoint 127.0.0.1:' + str(9000 + nodeIndex) +
        '    --max-clients ' + str(maxClients) +
        '    --p2p-max-nodes-per-host ' + str(maxClients) +
        '    --enable-stale-production'
        # '    --transaction-retry-max-storage-size-gb 5'
        '    --producer-name ' + account['name'] +
        '    --signature-provider ' + account['pub'] + '=KEY:' + account['pvt'] +
        '    --plugin eosio::http_plugin'
        '    --plugin eosio::chain_api_plugin'
        '    --plugin eosio::chain_plugin'
        '    --plugin eosio::producer_api_plugin'
        '    --plugin eosio::producer_plugin' +
        otherOpts)
    with open(dir + 'stderr', mode='w') as f:
        f.write(cmd + '\n\n')
    background(cmd + '    2>>' + dir + 'stderr')

def startDmNode():
    dir = args.nodes_dir + 'deepmind-node/'
    run('rm -rf ' + dir)
    run('mkdir -p ' + dir)
    otherOpts = ''
    cmd = (
        args.nodeos +
        '    --genesis-json ' + os.path.abspath(args.genesis_path) +
        '    --blocks-dir ' + os.path.abspath(dir) + '/blocks'
        '    --config-dir ' + os.path.abspath(dir) +
        '    --data-dir ' + os.path.abspath(dir) +
        '    --deep-mind ' +
        '    --contracts-console ' +
        '    --api-accept-transactions false ' +
        '    --p2p-accept-transactions false ' +
        '    --p2p-peer-address localhost:9000 ' +
        '    --p2p-listen-endpoint 0.0.0.0:7999 ' +
        otherOpts)
    with open(dir + 'stderr', mode='w') as f:
        f.write(cmd + '\n\n')
    background(cmd + '  1> '+os.path.abspath(args.dmlog_path) + ' 2>>' + dir + 'stderr')

def startProducers(b, e):
    for i in range(b, e):
        startNode(i - b + 1, accounts[i])

def createSystemAccounts():
    for a in systemAccounts:
        run(getCleos() + 'create account eosio ' + a + ' ' + args.public_key)

def intToCurrency(i):
    return '%d.%04d %s' % (i // 10000, i % 10000, args.symbol)

def allocateFunds(b, e):
    dist = [random.paretovariate(1.161) for _ in range(e - b)]
    dist.sort()
    dist.reverse()
    dist = list(map(float, dist))

    factor = 500_000_000 / sum(dist)
    total = 0
    for i in range(b, e):
        funds = round(factor * dist[i - b] * 10000)
        if i >= firstProducer and i < firstProducer + numProducers:
            funds = max(funds, round(args.min_producer_funds * 10000))
        total += funds
        accounts[i]['funds'] = funds
    return total

def createStakedAccounts(b, e):
    ramFunds = round(args.ram_funds * 10000)
    configuredMinStake = round(args.min_stake * 10000)
    maxUnstaked = round(args.max_unstaked * 10000)
    for i in range(b, e):
        a = accounts[i]
        funds = a['funds']
        print('#' * 80)
        print('# %d/%d %s %s' % (i, e, a['name'], intToCurrency(funds)))
        print('#' * 80)
        if funds < ramFunds:
            print('skipping %s: not enough funds to cover ram' % a['name'])
            continue
        minStake = min(funds - ramFunds, configuredMinStake)
        unstaked = min(funds - ramFunds - minStake, maxUnstaked)
        stake = funds - ramFunds - unstaked
        stakeNet = round(stake / 2)
        stakeCpu = stake - stakeNet
        print('%s: total funds=%s, ram=%s, net=%s, cpu=%s, unstaked=%s' % (a['name'], intToCurrency(a['funds']), intToCurrency(ramFunds), intToCurrency(stakeNet), intToCurrency(stakeCpu), intToCurrency(unstaked)))
        assert(funds == ramFunds + stakeNet + stakeCpu + unstaked)
        retry(getCleos() + 'system newaccount --transfer eosio %s %s --stake-net "%s" --stake-cpu "%s" --buy-ram "%s"   ' % 
            (a['name'], a['pub'], intToCurrency(stakeNet), intToCurrency(stakeCpu), intToCurrency(ramFunds)))
        if unstaked:
            retry(getCleos() + 'transfer eosio %s "%s"' % (a['name'], intToCurrency(unstaked)))

def regProducers(b, e):
    for i in range(b, e):
        a = accounts[i]
        retry(getCleos() + 'system regproducer ' + a['name'] + ' ' + a['pub'] + ' https://' + a['name'] + '.com' + '/' + a['pub'])

def listProducers():
    run(getCleos() + 'system listproducers')

def vote(b, e):
    for i in range(b, e):
        voter = accounts[i]['name']
        k = args.num_producers_vote
        if k > numProducers:
            k = numProducers - 1
        prods = random.sample(range(firstProducer, firstProducer + numProducers), k)
        prods = ' '.join(map(lambda x: accounts[x]['name'], prods))
        retry(getCleos(True) + 'system voteproducer prods ' + voter + ' ' + prods)

def claimRewards():
    table = getJsonOutput(getCleos(True) + 'get table eosio eosio producers -l 100')
    times = []
    for row in table['rows']:
        if row['unpaid_blocks'] and not row['last_claim_time']:
            times.append(getJsonOutput(getCleos(True) + 'system claimrewards -j ' + row['owner'])['processed']['elapsed'])
    print('Elapsed time for claimrewards:', times)

def proxyVotes(b, e):
    vote(firstProducer, firstProducer + 1)
    proxy = accounts[firstProducer]['name']
    retry(getCleos(True) + 'system regproxy ' + proxy)
    sleep(1.0)
    for i in range(b, e):
        voter = accounts[i]['name']
        retry(getCleos(True) + 'system voteproducer proxy ' + voter + ' ' + proxy)

def updateAuth(account, permission, parent, controller):
    run(getCleos(True) + 'push action eosio updateauth' + jsonArg({
        'account': account,
        'permission': permission,
        'parent': parent,
        'auth': {
            'threshold': 1, 'keys': [], 'waits': [],
            'accounts': [{
                'weight': 1,
                'permission': {'actor': controller, 'permission': 'active'}
            }]
        }
    }) + '-p ' + account + '@' + permission)

def resign(account, controller):
    updateAuth(account, 'owner', '', controller)
    updateAuth(account, 'active', 'owner', controller)
    sleep(1)
    run(getCleos(True) + 'get account ' + account)

def randomTransfer(b, e, num):
    for j in range(num):
        src = accounts[random.randint(b, e - 1)]['name']
        dest = src
        while dest == src:
            dest = accounts[random.randint(b, e - 1)]['name']
        trx_id = retry_with_id(getCleos(True) + 'transfer -f ' + src + ' ' + dest + ' "0.0001 ' + args.symbol + '" "transfer from ' + src + ' to ' + dest + '" || true')
        logAction(trx_id, 'eosio.token', src, 'transfer', { 'from': src, 'to': dest, 'quantity': '0.0001 ' + args.symbol, 'memo': 'transfer from ' + src + ' to ' + dest })
        logAction(trx_id, 'eosio.token', dest, 'transfer', { 'from': src, 'to': dest, 'quantity': '0.0001 ' + args.symbol, 'memo': 'transfer from ' + src + ' to ' + dest })
        sleep(0.5)

def msigProposeReplaceSystem(proposer, proposalName):
    requestedPermissions = []
    for i in range(firstProducer, firstProducer + numProducers):
        requestedPermissions.append({'actor': accounts[i]['name'], 'permission': 'active'})
    trxPermissions = [{'actor': 'eosio', 'permission': 'active'}]
    with open(fastUnstakeSystem, mode='rb') as f:
        setcode = {'account': 'eosio', 'vmtype': 0, 'vmversion': 0, 'code': f.read().hex()}
    run(getCleos(True) + 'multisig propose ' + proposalName + jsonArg(requestedPermissions) + 
        jsonArg(trxPermissions) + 'eosio setcode' + jsonArg(setcode) + ' -p ' + proposer)

def msigApproveReplaceSystem(proposer, proposalName):
    for i in range(firstProducer, firstProducer + numProducers):
        run(getCleos() + 'multisig approve ' + proposer + ' ' + proposalName +
            jsonArg({'actor': accounts[i]['name'], 'permission': 'active'}) +
            '-p ' + accounts[i]['name'])

def msigExecReplaceSystem(proposer, proposalName):
    retry(getCleos() + 'multisig exec ' + proposer + ' ' + proposalName + ' -p ' + proposer)

def msigReplaceSystem():
    run(getCleos() + 'push action eosio buyrambytes' + jsonArg(['eosio', accounts[0]['name'], 200000]) + '-p eosio')
    sleep(1)
    msigProposeReplaceSystem(accounts[0]['name'], 'fast.unstake')
    sleep(1)
    msigApproveReplaceSystem(accounts[0]['name'], 'fast.unstake')
    msigExecReplaceSystem(accounts[0]['name'], 'fast.unstake')

def produceNewAccounts():
    with open('newusers', 'w') as f:
        for i in range(120_000, 200_000):
            x = getOutput(getCleos() + 'create key --to-console')
            r = re.match('Private key: *([^ \n]*)\nPublic key: *([^ \n]*)', x, re.DOTALL | re.MULTILINE)
            name = 'user'
            for j in range(7, -1, -1):
                name += chr(ord('a') + ((i >> (j * 4)) & 15))
            print(i, name)
            f.write('        {"name":"%s", "pvt":"%s", "pub":"%s"},\n' % (name, r[1], r[2]))

def stepStartWallet():
    stepTitle()
    startWallet()
    importKeys()
def stepStartBoot():
    stepTitle()
    startNode(0, {'name': 'eosio', 'pvt': args.private_key, 'pub': args.public_key})
    sleep(10.0)
def stepStartDM():
    stepTitle()
    startDmNode()
    sleep(1)
def stepInstallSystemContracts():
    stepTitle()
    run(getCleos() + 'set contract eosio.token ' + args.contracts_dir + '/eosio.token/')
    run(getCleos() + 'set contract eosio.msig ' + args.contracts_dir + '/eosio.msig/')
def stepCreateTokens():
    stepTitle()
    run(getCleos() + 'push action eosio.token create \'["eosio", "10000000000.0000 %s"]\' -p eosio.token' % (args.symbol))
    totalAllocation = allocateFunds(0, len(accounts))
    run(getCleos() + 'push action eosio.token issue \'["eosio", "10000000000.0000 %s", "memo"]\' -p eosio' % (args.symbol))
    sleep(1)
def stepSetSystemContract():
    stepTitle()
    # All of the protocol upgrade features introduced in v1.8 first require a special protocol 
    # feature (codename PREACTIVATE_FEATURE) to be activated and for an updated version of the system 
    # contract that makes use of the functionality introduced by that feature to be deployed. 

    # activate PREACTIVATE_FEATURE before installing eosio.boot
    retry('curl -X POST http://127.0.0.1:%d' % args.http_port + 
        '/v1/producer/schedule_protocol_feature_activations ' +
        '-d \'{"protocol_features_to_activate": ["0ec7e080177b2c02b278d5088611686b49d739925a92d9bfcacd7fc6b74053bd"]}\'')
    sleep(3)

    # install eosio.boot which supports the native actions and activate 
    # action that allows activating desired protocol features prior to 
    # deploying a system contract with more features such as eosio.bios 
    # or eosio.system
    retry(getCleos() + 'set contract eosio ' + args.contracts_dir + '/eosio.boot/')
    sleep(3)

    # activate remaining features
    # ACTION_RETURN_VALUE
    retry(getCleos() + 'push action eosio activate \'["c3a6138c5061cf291310887c0b5c71fcaffeab90d5deb50d3b9e687cead45071"]\' -p eosio@active')
    # CONFIGURABLE_WASM_LIMITS2
    retry(getCleos() + 'push action eosio activate \'["d528b9f6e9693f45ed277af93474fd473ce7d831dae2180cca35d907bd10cb40"]\' -p eosio@active')
    # BLOCKCHAIN_PARAMETERS
    retry(getCleos() + 'push action eosio activate \'["5443fcf88330c586bc0e5f3dee10e7f63c76c00249c87fe4fbf7f38c082006b4"]\' -p eosio@active')
    # GET_SENDER
    retry(getCleos() + 'push action eosio activate \'["f0af56d2c5a48d60a4a5b5c903edfb7db3a736a94ed589d0b797df33ff9d3e1d"]\' -p eosio@active')
    # FORWARD_SETCODE
    retry(getCleos() + 'push action eosio activate \'["2652f5f96006294109b3dd0bbde63693f55324af452b799ee137a81a905eed25"]\' -p eosio@active')
    # ONLY_BILL_FIRST_AUTHORIZER
    retry(getCleos() + 'push action eosio activate \'["8ba52fe7a3956c5cd3a656a3174b931d3bb2abb45578befc59f283ecd816a405"]\' -p eosio@active')
    # RESTRICT_ACTION_TO_SELF
    retry(getCleos() + 'push action eosio activate \'["ad9e3d8f650687709fd68f4b90b41f7d825a365b02c23a636cef88ac2ac00c43"]\' -p eosio@active')
    # DISALLOW_EMPTY_PRODUCER_SCHEDULE
    retry(getCleos() + 'push action eosio activate \'["68dcaa34c0517d19666e6b33add67351d8c5f69e999ca1e37931bc410a297428"]\' -p eosio@active')
    # FIX_LINKAUTH_RESTRICTION
    retry(getCleos() + 'push action eosio activate \'["e0fb64b1085cc5538970158d05a009c24e276fb94e1a0bf6a528b48fbc4ff526"]\' -p eosio@active')
    # REPLACE_DEFERRED
    retry(getCleos() + 'push action eosio activate \'["ef43112c6543b88db2283a2e077278c315ae2c84719a8b25f25cc88565fbea99"]\' -p eosio@active')
    # NO_DUPLICATE_DEFERRED_ID
    retry(getCleos() + 'push action eosio activate \'["4a90c00d55454dc5b059055ca213579c6ea856967712a56017487886a4d4cc0f"]\' -p eosio@active')
    # ONLY_LINK_TO_EXISTING_PERMISSION
    retry(getCleos() + 'push action eosio activate \'["1a99a59d87e06e09ec5b028a9cbb7749b4a5ad8819004365d02dc4379a8b7241"]\' -p eosio@active')
    # RAM_RESTRICTIONS
    retry(getCleos() + 'push action eosio activate \'["4e7bf348da00a945489b2a681749eb56f5de00b900014e137ddae39f48f69d67"]\' -p eosio@active')
    # WEBAUTHN_KEY
    retry(getCleos() + 'push action eosio activate \'["4fca8bd82bbd181e714e283f83e1b45d95ca5af40fb89ad3977b653c448f78c2"]\' -p eosio@active')
    # WTMSIG_BLOCK_SIGNATURES
    retry(getCleos() + 'push action eosio activate \'["299dcb6af692324b899b39f16d5a530a33062804e41f09dc97e9f156b4476707"]\' -p eosio@active')
    # GET_CODE_HASH
    retry(getCleos() + 'push action eosio activate \'["bcd2a26394b36614fd4894241d3c451ab0f6fd110958c3423073621a70826e99"]\' -p eosio@active')
    # GET_BLOCK_NUM
    retry(getCleos() + 'push action eosio activate \'["35c2186cc36f7bb4aeaf4487b36e57039ccf45a9136aa856a5d569ecca55ef2b"]\' -p eosio@active')
    # CRYPTO_PRIMITIVES
    retry(getCleos() + 'push action eosio activate \'["6bcb40a24e49c26d0a60513b6aeb8551d264e4717f306b81a37a5afb3b47cedc"]\' -p eosio@active')
    sleep(1)

    # install eosio.system latest version
    retry(getCleos() + 'set contract eosio ' + args.contracts_dir + '/eosio.system/')
    # setpriv is only available after eosio.system is installed
    run(getCleos() + 'push action eosio setpriv' + jsonArg(['eosio.msig', 1]) + '-p eosio@active')
    sleep(3)
# "EOS5MHPYyhjBjnQZejzZHqHewPWhGTfQWSVTWYEhDmJu4SXkzgweP"
def stepBattlefield():
    stepTitle()

    trx_id = retry_with_id(getCleos() + 'set account permission battlefield1 active --add-code')
    logAction(trx_id, 'eosio', 'eosio', 'updateauth', { 'account': 'battlefield1', 'auth': '*', 'parent': 'owner', 'permission': 'active' })
    retry(getCleos() + 'set account permission battlefield2 active --add-code')
    retry(getCleos() + 'set account permission battlefield3 active --add-code')
    retry(getCleos() + 'set account permission battlefield4 active --add-code')
    retry(getCleos() + 'set account permission notified2 active --add-code')
    retry(getCleos() + 'set account permission battlefield5 active \'{ \
        "threshold": 5, \
        "keys": [], \
        "waits": [{"wait_sec": 10800, "weight": 1}], \
        "accounts": [ \
            {"permission":{"actor":"battlefield1","permission":"active"},"weight":2},\
            {"permission":{"actor":"battlefield3","permission":"active"},"weight":2},\
            {"permission":{"actor":"battlefield4","permission":"active"},"weight":2},\
            {"permission":{"actor":"zzzzzzzzzzzz","permission":"active"},"weight":1}\
        ]}\' \
    ')
    retry(getCleos() + 'set account permission battlefield5 day2day \'{ \
        "threshold": 1, \
        "keys": [], \
        "accounts": [ \
            {"permission":{"actor":"battlefield1","permission":"active"},"weight":1},\
            {"permission":{"actor":"battlefield3","permission":"active"},"weight":1},\
            {"permission":{"actor":"battlefield4","permission":"active"},"weight":1}\
        ]}\' \
    ')
    
    print('\nSetting contracts')
    trx_id = retry_with_id(getCleos() + 'system buyram eosio battlefield1 --kbytes 20000')
    logAction(trx_id, 'eosio', 'eosio', 'buyrambytes', { 'bytes': 20480000, 'payer': 'eosio', 'receiver': 'battlefield1' })
    logDbop(trx_id, 'eosio', 'eosio', 'rammarket', 'cpd4ykuhc5d.4', 'UPD', {"base":{"balance":"68718246002 RAM","weight":"0.50000000000000000"},"quote":{"balance":"10000179.1000 SYS","weight":"0.50000000000000000"},"supply":"10000000000.0000 RAMCORE"})
    logDbop(trx_id, 'eosio', 'battlefield1', 'userres', 'battlefield1', 'UPD', {"cpu_weight":"*","net_weight":"*","owner":"battlefield1","ram_bytes":"*"})
    trx_id = retry_with_id(getCleos() + 'system buyram eosio battlefield3 --kbytes 1000')
    logAction(trx_id, 'eosio', 'eosio', 'buyrambytes', { 'bytes': 1024000, 'payer': 'eosio', 'receiver': 'battlefield3' })
    trx_id = retry_with_id(getCleos() + 'system buyram eosio notified2 --kbytes 1000')
    logAction(trx_id, 'eosio', 'eosio', 'buyrambytes', { 'bytes': 1024000, 'payer': 'eosio', 'receiver': 'notified2' })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'set contract battlefield1 ./battlefield battlefield.wasm battlefield.abi')
    logAction(trx_id, 'eosio', 'eosio', 'setcode', { 'account': 'battlefield1', 'code': '*', 'vmtype': 0, 'vmversion': 0 })
    sleep(0.3)
    trx_id = retry_with_id(getCleos() + 'set contract battlefield3 ./battlefield battlefield.wasm battlefield.abi')
    logAction(trx_id, 'eosio', 'eosio', 'setcode', { 'account': 'battlefield3', 'code': '*', 'vmtype': 0, 'vmversion': 0 })
    sleep(0.3)
    trx_id = retry_with_id(getCleos() + 'set contract notified2 ./battlefield battlefield.wasm battlefield.abi')
    logAction(trx_id, 'eosio', 'eosio', 'setcode', { 'account': 'notified2', 'code': '*', 'vmtype': 0, 'vmversion': 0 })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 prims \'{"boolvar": true, "namevar": "battlefield1", "stringvar": "some string", "int8var": -1, "uint8var": 2, "int16var": -3, "uint16var": 4, "int32var": -5, "uint32var": 6, "int64var": -7, "uint64var": 8, "doublevar": 9.12345678900000046, "floatvar": 10.12345027923583984}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'prims', { 'boolvar': 1, 'namevar': 'battlefield1', 'stringvar': 'some string', 'int8var': -1, 'uint8var': 2, 'int16var': -3, 'uint16var': 4, 'int32var': -5, 'uint32var': 6, 'int64var': -7, 'uint64var': 8, 'doublevar': '9.12345678900000046', 'floatvar': '10.12345027923583984' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'primitives', '', 'INS', { 'id': 0, 'boolvar': 1, 'namevar': 'battlefield1', 'stringvar': 'some string', 'int8var': -1, 'uint8var': 2, 'int16var': -3, 'uint16var': 4, 'int32var': -5, 'uint32var': 6, 'int64var': -7, 'uint64var': 8, 'doublevar': "9.12345678900000046", 'floatvar': "10.12345027923583984" })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 prims \'{"boolvar": false, "namevar": "battlefield1", "stringvar": "some string", "int8var": -1, "uint8var": 2, "int16var": -3, "uint16var": 4, "int32var": -5, "uint32var": 6, "int64var": -7, "uint64var": 8, "doublevar": 9.12345678900000046, "floatvar": 10.12345027923583984}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'prims', { 'boolvar': 0, 'namevar': 'battlefield1', 'stringvar': 'some string', 'int8var': -1, 'uint8var': 2, 'int16var': -3, 'uint16var': 4, 'int32var': -5, 'uint32var': 6, 'int64var': -7, 'uint64var': 8, 'doublevar': '9.12345678900000046', 'floatvar': '10.12345027923583984' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'primitives', '............1', 'INS', { 'id': 1, 'boolvar': 0, 'namevar': 'battlefield1', 'stringvar': 'some string', 'int8var': -1, 'uint8var': 2, 'int16var': -3, 'uint16var': 4, 'int32var': -5, 'uint32var': 6, 'int64var': -7, 'uint64var': 8, 'doublevar': "9.12345678900000046", 'floatvar': "10.12345027923583984" })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 setprim \'{"id": 0, "boolvar": false}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'setprim', { 'boolvar': 0 })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'primitives', '', 'UPD', { 'id': 0, 'boolvar': 0})
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 setprim \'{"id": 1, "boolvar": true}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'setprim', { 'boolvar': 1 })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'primitives', '............1', 'UPD', { 'id': 1, 'boolvar': 1})
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 bltins \'{"symcodevar": "EOS", "assetvar": "1.0000 EOS", "symbolvar": "4,EOS", "extsymvar": {"contract": "eosio.token", "sym": "4,EOS"}, "extassetvar": {"contract": "eosio.token", "quantity": "1.0000 EOS"}, "vecvar": ["battlefield1", "battlefield2"], "mapvar": [{"first": "k1", "second": "v1"}, {"first": "k2", "second": "v2"}], "timevar": "2023-01-02T03:04:05", "vari1": ["uint16", 20], "vari2": ["string", "vari string"]}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'bltins', { 'symcodevar': 'EOS', 'assetvar': '1.0000 EOS', 'symbolvar': '4,EOS', 'extsymvar': {"contract": "eosio.token", "sym": "4,EOS"}, "extassetvar": {"contract": "eosio.token", "quantity": "1.0000 EOS"}, "vecvar": ["battlefield1", "battlefield2"], "mapvar": [{"first": "k1", "second": "v1"}, {"first": "k2", "second": "v2"}], "timevar": "2023-01-02T03:04:05", "vari1": ["uint16", 20], "vari2": ["string", "vari string"]})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'builtins', '', 'INS', { 'id': 0, 'symcodevar': 'EOS', 'assetvar': '1.0000 EOS', 'symbolvar': '4,EOS', 'extsymvar': {"contract": "eosio.token", "sym": "4,EOS"}, "extassetvar": {"contract": "eosio.token", "quantity": "1.0000 EOS"}, "vecvar": ["battlefield1", "battlefield2"], "mapvar": [{"first": "k1", "second": "v1"}, {"first": "k2", "second": "v2"}], "timevar": "2023-01-02T03:04:05", "vari1": ["uint16", 20], "vari2": ["string", "vari string"] })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 complex \'{"nested": {"nested_id": 123, "nested_vari": [["uint16", 20],["string", "vari string"]]}, "vari": [["uint16", 20],["string", "vari string"]]}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'complex', {"nested": {"nested_id": 123, "nested_vari": [["uint16", 20],["string", "vari string"]]}, "vari": [["uint16", 20],["string", "vari string"]]})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'complex', '', 'INS', { 'id': 0, 'nested': {"nested_id": 123, "nested_vari": [["uint16", 20],["string", "vari string"]]}, "vari": [["uint16", 20],["string", "vari string"]] })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dbins \'{"account": "battlefield1"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dbins', { 'account': 'battlefield1' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '............1', 'INS', { "account": "dbops1", "amount": "0 ", "created_at": "*", "expires_at": "1970-01-01T00:00:00", "id": 1, "memo": "inserted billed to calling account"})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '............2', 'INS', { "account": "dbops2", "amount": "0 ", "created_at": "*", "expires_at": "1970-01-01T00:00:00", "id": 2, "memo": "inserted billed to self"})
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dbupd \'{"account": "battlefield2"}\' -p battlefield2')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dbupd', { 'account': 'battlefield2' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '............1', 'UPD', { "account": "dbops1", "amount": "0 ", "created_at": "*", "expires_at": "1970-01-01T00:00:00", "id": 1, "memo": "updated row 1"})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '............2', 'UPD', { "account": "dbupd", "amount": "0 ", "created_at": "*", "expires_at": "1970-01-01T00:00:00", "id": 2, "memo": "updated row 2"})
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dbrem \'{"account": "battlefield1"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dbrem', { 'account': 'battlefield1' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '............1', 'REM', {})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '............2', 'REM', {})
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dtrx \'{"account": "battlefield1", "fail_now": false, "fail_later": false, "fail_later_nested": false, "delay_sec": 1, "nonce": "1"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dtrx', { "account": "battlefield1", "delay_sec": 1, "fail_later": 0, "fail_later_nested": 0, "fail_now": 0, "nonce": "1" })
    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dtrxcancel \'{"account": "battlefield1"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dtrxcancel', { 'account': 'battlefield1' })
    sleep(1)

    # background(getCleos() + 'push action battlefield1 dtrx \'{"account": "battlefield1", "fail_now": true, "fail_later": false, "fail_later_nested": false, "delay_sec": 1, "nonce": "1"}\' -p battlefield1')
    # print("\nThe error message you see above ^^^ is OK, we were expecting the transaction to fail, continuing....")
    # sleep(0.6)

    # `send_deferred` with `replace_existing` enabled, to test `MODIFY` clauses.
    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dtrx \'{"account": "battlefield1", "fail_now": false, "fail_later": false, "fail_later_nested": false, "delay_sec": 1, "nonce": "1"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dtrx', { "account": "battlefield1", "delay_sec": 1, "fail_later": 0, "fail_later_nested": 0, "fail_now": 0, "nonce": "1" })
    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dtrx \'{"account": "battlefield1", "fail_now": false, "fail_later": false, "fail_later_nested": false, "delay_sec": 1, "nonce": "2"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dtrx', { "account": "battlefield1", "delay_sec": 1, "fail_later": 0, "fail_later_nested": 0, "fail_now": 0, "nonce": "2" })
    sleep (0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dtrx \'{"account": "battlefield1", "fail_now": false, "fail_later": true, "fail_later_nested": false, "delay_sec": 1, "nonce": "1"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dtrx', { "account": "battlefield1", "delay_sec": 1, "fail_later": 1, "fail_later_nested": 0, "fail_now": 0, "nonce": "1" })
    print('\nWaiting for the transaction to fail (no onerror handler)...')
    sleep(1.1)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dtrx \'{"account": "battlefield1", "fail_now": false, "fail_later": false, "fail_later_nested": true, "delay_sec": 1, "nonce": "2"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dtrx', { "account": "battlefield1", "delay_sec": 1, "fail_later": 0, "fail_later_nested": 1, "fail_now": 0, "nonce": "2" })
    print('\nWaiting for the transaction to fail (no onerror handler)...')
    sleep(1.1)

    trx_id = retry_with_id(getCleos() + 'push action battlefield3 dtrx \'{"account": "battlefield3", "fail_now": false, "fail_later": true, "fail_later_nested": false, "delay_sec": 1, "nonce": "1"}\' -p battlefield3')
    logAction(trx_id, 'battlefield3', 'battlefield3', 'dtrx', { "account": "battlefield3", "delay_sec": 1, "fail_later": 1, "fail_later_nested": 0, "fail_now": 0, "nonce": "1" })
    # soft error
    # logAction(trx_id, 'eosio', 'battlefield3', 'onerror', { 'sender_id': '*', 'sent_trx': '*' })
    print('\nWaiting for the transaction to fail (with onerror handler that succeed)...')
    sleep(1.1)

    trx_id = retry_with_id(getCleos() + 'push action battlefield3 dtrx \'{"account": "battlefield3", "fail_now": false, "fail_later": true, "fail_later_nested": false, "delay_sec": 1, "nonce": "f"}\' -p battlefield3')
    logAction(trx_id, 'battlefield3', 'battlefield3', 'dtrx', { "account": "battlefield3", "delay_sec": 1, "fail_later": 1, "fail_later_nested": 0, "fail_now": 0, "nonce": "f" })
    # soft error
    # logAction(trx_id, 'eosio', 'battlefield3', 'onerror', { 'sender_id': '*', 'sent_trx': '*' })
    print('\nWaiting for the transaction to fail (with onerror handler that failed)...')
    sleep(1.1)

    trx_id = retry_with_id(getCleos() + 'push action battlefield3 dtrx \'{"account": "battlefield3", "fail_now": false, "fail_later": true, "fail_later_nested": false, "delay_sec": 1, "nonce": "nf"}\' -p battlefield3')
    logAction(trx_id, 'battlefield3', 'battlefield3', 'dtrx', { "account": "battlefield3", "delay_sec": 1, "fail_later": 1, "fail_later_nested": 0, "fail_now": 0, "nonce": "nf" })
    print('\nWaiting for the transaction to fail (with onerror handler that failed inside a nested action)...')
    sleep(1.1)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 dbinstwo \'{"account": "battlefield1", "first": 100, "second": 101}\' -p battlefield1')
    # ?????
    # This TX will do one DB_OPERATION for writing, and the second will fail. We want our instrumentation NOT to keep that DB_OPERATION.
    logAction(trx_id, 'battlefield1', 'battlefield1', 'dbinstwo', { 'account': 'battlefield1', 'first': 100, 'second': 101 })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '...........a4', 'INS', { "account": "...........a4", "amount": "0 ", "created_at": "*", "expires_at": "1970-01-01T00:00:00", "id": 100, "memo": "inserted billed to calling account"})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '...........a5', 'INS', { "account": "...........a5", "amount": "0 ", "created_at": "*", "expires_at": "1970-01-01T00:00:00", "id": 101, "memo": "inserted billed to self"})
    
    # Defered transactions deprecated

    # trx_id = retry_with_id(getCleos() + 'push action --delay-sec=1 battlefield1 dbinstwo \'{"account": "battlefield1", "first": 102, "second": 100}\' -p battlefield1')
    # # this one fails, nothing on chain
    # print('\nWaiting for the transaction to fail, yet attempt to write to storage')
    # sleep(1.1)

    # trx_id = retry_with_id(getCleos() + 'push action battlefield1 dbremtwo \'{"account": "battlefield1", "first": 100, "second": 101}\' -p battlefield1')
    # # This TX will show a delay transaction (deferred) that succeeds
    # retry(getCleos() + 'push action --delay-sec=1 eosio.token transfer \'{"from": "eosio", "to": "battlefield1", "quantity": "1.0000 SYS", "memo":"push delayed trx"}\' -p eosio')
    # logAction(trx_id, 'battlefield1', 'battlefield1', 'dbremtwo', { 'account': 'battlefield1', 'first': 100, 'second': 101 })
    # logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '...........a4', 'REM', {})
    # logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '...........a5', 'REM', {})
    # sleep(1.1)

    # # This is to see how the RAM_USAGE behaves, when a deferred hard_fails. Does it refund the deferred_trx_remove ? What about the other RAM tweaks? Any one them saved?
    # trx_id = retry_with_id(getCleos() + 'push action battlefield1 dbinstwo \'{"account": "battlefield1", "first": 200, "second": 201}\' -p battlefield1')
    # logAction(trx_id, 'battlefield1', 'battlefield1', 'dbinstwo', { 'account': 'battlefield1', 'first': 200, 'second': 201 })
    # logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '...........gc', 'INS', { "account": "...........gc", "amount": "0 ", "created_at": "*", "expires_at": "1970-01-01T00:00:00", "id": 100, "memo": "inserted billed to calling account"})
    # logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '...........gd', 'INS', { "account": "...........gd", "amount": "0 ", "created_at": "*", "expires_at": "1970-01-01T00:00:00", "id": 101, "memo": "inserted billed to self"})
    # print('\n')

    # sleep(0.6)
    # trx_id = retry_with_id(getCleos() + 'push action battlefield1 dbremtwo \'{"account": "battlefield1", "first": 200, "second": 201}\' -p battlefield1')
    # logAction(trx_id, 'battlefield1', 'battlefield1', 'dbremtwo', { 'account': 'battlefield1', 'first': 200, 'second': 201 })
    # logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '...........gc', 'REM', {})
    # logDbop(trx_id, 'battlefield1', 'battlefield1', 'member', '...........gd', 'REM', {})

    # # Create a delayed and cancel it (in same block) with \'eosio:canceldelay\''
    # trx_id = retry_with_id(getCleos() + 'push action --delay-sec=3600 battlefield1 dbins \'{"account": "battlefield1"}\' -p battlefield1 --json-file /tmp/delayed.json')
    # with open('/tmp/delayed.json', 'r') as file:
    #     data = json.load(file)
    # retry(getCleos() + 'system canceldelay battlefield1 active ' + data["transaction_id"])
    # retry('rm /tmp/delayed.json || true')
    # sleep(0.6)

    # # Create a delayed and cancel it (in the next block) with \'eosio:canceldelay\''
    # trx_id = retry_with_id(getCleos() + 'push action --delay-sec=3600 battlefield1 dbins \'{"account": "battlefield1"}\' -p battlefield1 --json-file /tmp/delayed.json')
    # with open('/tmp/delayed.json', 'r') as file:
    #     data = json.load(file)
    # sleep(1.1)
    # retry(getCleos() + 'system canceldelay battlefield1 active ' + data["transaction_id"])
    # retry('rm /tmp/delayed.json || true')
    # sleep(0.6)

    print('\nCreate auth structs, updateauth to create, updateauth to modify, deleteauth to test AUTH_OPs')
    # random key
    trx_id = retry_with_id(getCleos() + 'set account permission battlefield2 ops EOS7f5watu1cLgth3ub1uAnsGkHq1F6PhauScBg6rJGUfe79MgG9Y active')
    logAction(trx_id, 'eosio', 'eosio', 'updateauth', { 'account': 'battlefield2', 'auth': '*', 'parent': 'active', 'permission': 'ops' })
    sleep(0.6)
    # back to safe key
    trx_id = retry_with_id(getCleos() + 'set account permission battlefield2 ops EOS5MHPYyhjBjnQZejzZHqHewPWhGTfQWSVTWYEhDmJu4SXkzgweP')
    logAction(trx_id, 'eosio', 'eosio', 'updateauth', { 'account': 'battlefield2', 'auth': '*', 'parent': 'active', 'permission': 'ops' })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'set action permission battlefield2 eosio.token transfer ops')
    logAction(trx_id, 'eosio', 'eosio', 'linkauth', { 'account': 'battlefield2', 'code': 'eosio.token', 'requirement': 'ops', 'type': 'transfer' })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'set action permission battlefield2 eosio.token transfer NULL')
    logAction(trx_id, 'eosio', 'eosio', 'unlinkauth', { 'account': 'battlefield2', 'code': 'eosio.token', 'type': 'transfer' })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'set account permission battlefield2 ops NULL')
    logAction(trx_id, 'eosio', 'eosio', 'deleteauth', { 'account': 'battlefield2', 'permission': 'ops' })
    sleep(0.6)

    print("\nCreate a creational order different than the execution order")
    ## We use the --force-unique flag so a context-free action exist in the transactions traces tree prior our own,
    ## creating a multi-root execution traces tree.
    trx_id = retry_with_id(getCleos() + 'push action --force-unique battlefield1 creaorder \'{"n1": "notified1", "n2": "notified2", "n3": "notified3", "n4": "notified4", "n5": "notified5"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'creaorder', { 'n1': 'notified1', 'n2': 'notified2', 'n3': 'notified3', 'n4': 'notified4', 'n5': 'notified5' })
    logAction(trx_id, 'battlefield1', 'notified1', 'creaorder', { 'n1': 'notified1', 'n2': 'notified2', 'n3': 'notified3', 'n4': 'notified4', 'n5': 'notified5' })
    logAction(trx_id, 'battlefield1', 'notified2', 'creaorder', { 'n1': 'notified1', 'n2': 'notified2', 'n3': 'notified3', 'n4': 'notified4', 'n5': 'notified5' })
    logAction(trx_id, 'battlefield1', 'notified3', 'creaorder', { 'n1': 'notified1', 'n2': 'notified2', 'n3': 'notified3', 'n4': 'notified4', 'n5': 'notified5' })
    logAction(trx_id, 'eosio.null', 'eosio.null', 'nonce', {})
    logAction(trx_id, 'eosio.null', 'eosio.null', 'nonce', {})
    logAction(trx_id, 'battlefield1', 'battlefield1', 'inlinedeep', { 'n4': 'notified4', 'n5': 'notified5', 'nestedCfaInlineTag': 'c3', 'nestedInlineFail': 0, 'nestedInlineTag': 'i3', 'tag': 'i2' })
    logAction(trx_id, 'battlefield1', 'notified4', 'inlinedeep', { 'n4': 'notified4', 'n5': 'notified5', 'nestedCfaInlineTag': 'c3', 'nestedInlineFail': 0, 'nestedInlineTag': 'i3', 'tag': 'i2' })
    logAction(trx_id, 'battlefield1', 'notified5', 'inlinedeep', { 'n4': 'notified4', 'n5': 'notified5', 'nestedCfaInlineTag': 'c3', 'nestedInlineFail': 0, 'nestedInlineTag': 'i3', 'tag': 'i2' })
    logAction(trx_id, 'eosio.null', 'eosio.null', 'nonce', {})
    logAction(trx_id, 'battlefield1', 'battlefield1', 'inlineempty', { 'fail': 0, 'tag': 'i3' })
    logAction(trx_id, 'battlefield1', 'battlefield1', 'inlineempty', { 'fail': 0, 'tag': 'i1' })
    
    # TODO
    sleep(0.6)

    ## Series of test for variant support
    trx_id = retry_with_id(getCleos() + 'push action battlefield1 varianttest \'{"value":["uint16",12]}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'varianttest', { 'value': ['uint16', 12] })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'variant', '', 'INS', { 'creation_number': '*', 'id': 0, 'variant_field': ['uint16', 12] })
    trx_id = retry_with_id(getCleos() + 'push action battlefield1 varianttest \'{"value":["string","this is a long value"]}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'varianttest', { 'value': ['string', 'this is a long value'] })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'variant', '............1', 'INS', { 'creation_number': '*', 'id': 1, 'variant_field': ['string', 'this is a long value'] })
    sleep(0.6)

    ## Series of test for secondary keys
    trx_id = retry_with_id(getCleos() + 'push action battlefield1 sktest \'{"action":"insert"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'sktest', { 'action': 'insert' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.i', '', 'INS', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000000000000000000000', "d64":"0.00000000000000000","i128":"0","i64":1,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.ii', '', 'INS', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000000000000000000000', "d64":"0.00000000000000000","i128":"2","i64":0,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.d', '', 'INS', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000000000000000000000', "d64":"3.10000000000000009","i128":"0","i64":0,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.dd', '', 'INS', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000606666666666260140', "d64":"0.00000000000000000","i128":"0","i64":0,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.c', '', 'INS', { 'c256': '00000000000000000000000000000005ffaabb00ddee11220033445500ffaa22', 'd128': '0x00000000000000000000000000000000', "d64":"0.00000000000000000","i128":"0","i64":0,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.multi', '', 'INS', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000606666666666260140', "d64":"3.10000000000000009","i128":"2","i64":1,"id":0,"unrelated":0})
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 sktest \'{"action":"update.sk"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'sktest', { 'action': 'update.sk' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.i', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000000000000000000000', "d64":"0.00000000000000000","i128":"0","i64":2,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.ii', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000000000000000000000', "d64":"0.00000000000000000","i128":"4","i64":0,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.d', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000000000000000000000', "d64":"6.30000000000000071","i128":"0","i64":0,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.dd', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000989999999999290240', "d64":"0.00000000000000000","i128":"0","i64":0,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.c', '', 'UPD', { 'c256': '0000000000000000000000000000000affaabb00ddee11220033445500ffaa22', 'd128': '0x00000000000000000000000000000000', "d64":"0.00000000000000000","i128":"0","i64":0,"id":0,"unrelated":0})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.multi', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000989999999999290240', "d64":"6.30000000000000071","i128":"4","i64":2,"id":0,"unrelated":0})
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 sktest \'{"action":"update.ot"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'sktest', { 'action': 'update.ot' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.i', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000000000000000000000', "d64":"0.00000000000000000","i128":"0","i64":2,"id":0,"unrelated":1})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.ii', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000000000000000000000', "d64":"0.00000000000000000","i128":"4","i64":0,"id":0,"unrelated":2})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.d', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000000000000000000000', "d64":"6.30000000000000071","i128":"0","i64":0,"id":0,"unrelated":3})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.dd', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000989999999999290240', "d64":"0.00000000000000000","i128":"0","i64":0,"id":0,"unrelated":4})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.c', '', 'UPD', { 'c256': '0000000000000000000000000000000affaabb00ddee11220033445500ffaa22', 'd128': '0x00000000000000000000000000000000', "d64":"0.00000000000000000","i128":"0","i64":0,"id":0,"unrelated":5})
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.multi', '', 'UPD', { 'c256': '0000000000000000000000000000000000000000000000000000000000000000', 'd128': '0x00000000000000989999999999290240', "d64":"6.30000000000000071","i128":"4","i64":2,"id":0,"unrelated":6})
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 sktest \'{"action":"remove"}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'sktest', { 'action': 'remove' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.i', '', 'UPD', { })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.ii', '', 'UPD', { })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.d', '', 'UPD', { })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.dd', '', 'UPD', { })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.c', '', 'UPD', { })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'sk.multi', '', 'UPD', { })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 retvalue \'{"n":100}\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'retvalue', { 'n': 100 })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 binexttest \'[bintest]\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'binexttest', { 'data': 'bintest' })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'binaryext', '', 'INS', { 'binext_field': 'bintest', 'id': 0 })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 binexttest \'[]\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'binexttest', { })
    logDbop(trx_id, 'battlefield1', 'battlefield1', 'binaryext', '............1', 'INS', { 'binext_field': '', 'id': 1 })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 optiontest \'[opti]\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'optiontest', { 'opt_param': 'opti' })
    sleep(0.6)

    trx_id = retry_with_id(getCleos() + 'push action battlefield1 optiontest \'[null]\' -p battlefield1')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'optiontest', { 'opt_param': 'null' })
    sleep(0.6)

    # create a bunch of rows
    trx_id = retry_with_id(getCleos() + 'push action battlefield1 producerows \'{"row_count": 100}\' -p battlefield1 > /dev/null')
    logAction(trx_id, 'battlefield1', 'battlefield1', 'producerows', { 'row_count': 100 })

    
    sleep(3)


def stepInitSystemContract():
    stepTitle()
    run(getCleos() + 'push action eosio init' + jsonArg(['0', '4,' + args.symbol]) + '-p eosio@active')
    sleep(1)
def stepCreateStakedAccounts():
    stepTitle()
    createStakedAccounts(0, len(accounts))
def stepRegProducers():
    stepTitle()
    regProducers(firstProducer, firstProducer + numProducers)
    sleep(1)
    listProducers()
def stepStartProducers():
    stepTitle()
    startProducers(firstProducer, firstProducer + numProducers)
    sleep(args.producer_sync_delay)
def stepVote():
    stepTitle()
    vote(0, 0 + args.num_voters)
    sleep(1)
    listProducers()
    sleep(5)
def stepProxyVotes():
    stepTitle()
    proxyVotes(0, 0 + args.num_voters)
def stepResign():
    stepTitle()
    resign('eosio', 'eosio.prods')
    for a in systemAccounts:
        resign(a, 'eosio')
def stepTransfer():
    stepTitle()
    randomTransfer(0, args.num_senders, 5)
def stepLog():
    stepTitle()
    run('tail -n 60 ' + args.nodes_dir + '00-eosio/stderr')
def stepKillall():
    stepTitle()
    run('killall nodeos keosd || true')
    sleep(1)
    
# Command Line Arguments

parser = argparse.ArgumentParser()

commands = [
    ('w', 'wallet',             stepStartWallet,            True,    "Start keosd, create wallet, fill with keys"),
    ('b', 'boot',               stepStartBoot,              True,    "Start boot node"),
    ('d', 'dm',                 stepStartDM,                True,    "Start deep-mind node"),
    ('s', 'sys',                createSystemAccounts,       True,    "Create system accounts (eosio.*)"),
    ('c', 'contracts',          stepInstallSystemContracts, True,    "Install system contracts (token, msig)"),
    ('t', 'tokens',             stepCreateTokens,           True,    "Create tokens"),
    ('S', 'sys-contract',       stepSetSystemContract,      True,    "Set system contract"),
    ('I', 'init-sys-contract',  stepInitSystemContract,     True,    "Initialiaze system contract"),
    ('T', 'stake',              stepCreateStakedAccounts,   True,    "Create staked accounts"),
    ('p', 'reg-prod',           stepRegProducers,           True,    "Register producers"),
    ('P', 'start-prod',         stepStartProducers,         True,    "Start producers"),
    ('v', 'vote',               stepVote,                   True,    "Vote for producers"),
    ('R', 'claim',              claimRewards,               True,    "Claim rewards"),
    ('x', 'proxy',              stepProxyVotes,             True,    "Proxy votes"),
    ('q', 'resign',             stepResign,                 True,    "Resign eosio"),
    ('f', 'battlefield',        stepBattlefield,            True,    "Run battlefield tests"),
    ('m', 'msg-replace',        msigReplaceSystem,          False,   "Replace system contract using msig"),
    ('X', 'xfer',               stepTransfer,               True,    "Random transfer tokens"),
    ('l', 'log',                stepLog,                    True,    "Show tail of node's log"),
    ('k', 'killall',            stepKillall,                False,    "Killall in the end"),
]

parser.add_argument('--public-key', metavar='', help="EOSIO Public Key", default='EOS8Znrtgwt8TfpmbVpTKvA2oB8Nqey625CLN8bCN3TEbgx86Dsvr', dest="public_key")
parser.add_argument('--private-Key', metavar='', help="EOSIO Private Key", default='5K463ynhZoCDDa4RDcr63cUwWLTnKqmdcoTKTHBjqoKfv4u5V7p', dest="private_key")
parser.add_argument('--cleos', metavar='', help="Cleos command", default='../../build/programs/cleos/cleos --wallet-url http://127.0.0.1:6666 ')
parser.add_argument('--nodeos', metavar='', help="Path to nodeos binary", default='../../build/programs/nodeos/nodeos')
parser.add_argument('--keosd', metavar='', help="Path to keosd binary", default='../../build/programs/keosd/keosd')
parser.add_argument('--contracts-dir', metavar='', help="Path to latest contracts directory", default='../../build/contracts/')
parser.add_argument('--old-contracts-dir', metavar='', help="Path to 1.8.x contracts directory", default='../../build/contracts/')
parser.add_argument('--nodes-dir', metavar='', help="Path to nodes directory", default='./nodes/')
parser.add_argument('--genesis-path', metavar='', help="Path to genesis.json", default="./genesis.json")
parser.add_argument('--accounts-path', metavar='', help="Path to accounts.json", default="./accounts.json")
parser.add_argument('--wallet-dir', metavar='', help="Path to wallet directory", default='./wallet/')
parser.add_argument('--log-path', metavar='', help="Path to log file", default='./output.log')
parser.add_argument('--actionlog-path', metavar='', help="Path to action log file", default='./expected.jsonl')
parser.add_argument('--dmlog-path', metavar='', help="Path to deepmind log file", default='./dm.log')
parser.add_argument('--symbol', metavar='', help="The eosio.system symbol", default='SYS')
parser.add_argument('--user-limit', metavar='', help="Max number of users. (0 = no limit)", type=int, default=3000)
parser.add_argument('--max-user-keys', metavar='', help="Maximum user keys to import into wallet", type=int, default=100)
parser.add_argument('--ram-funds', metavar='', help="How much funds for each user to spend on ram", type=float, default=10)
parser.add_argument('--min-stake', metavar='', help="Minimum stake before allocating unstaked funds", type=float, default=0.9)
parser.add_argument('--max-unstaked', metavar='', help="Maximum unstaked funds", type=float, default=10)
parser.add_argument('--producer-limit', metavar='', help="Maximum number of producers. (0 = no limit)", type=int, default=0)
parser.add_argument('--min-producer-funds', metavar='', help="Minimum producer funds", type=float, default=1000.0000)
parser.add_argument('--num-producers-vote', metavar='', help="Number of producers for which each user votes", type=int, default=20)
parser.add_argument('--num-voters', metavar='', help="Number of voters", type=int, default=10)
parser.add_argument('--num-senders', metavar='', help="Number of users to transfer funds randomly", type=int, default=10)
parser.add_argument('--producer-sync-delay', metavar='', help="Time (s) to sleep to allow producers to sync", type=int, default=80)
parser.add_argument('-a', '--all', action='store_true', help="Do everything marked with (*)")
parser.add_argument('-H', '--http-port', type=int, default=8000, metavar='', help='HTTP port for cleos')

for (flag, command, function, inAll, help) in commands:
    prefix = ''
    if inAll: prefix += '*'
    if prefix: help = '(' + prefix + ') ' + help
    if flag:
        parser.add_argument('-' + flag, '--' + command, action='store_true', help=help, dest=command)
    else:
        parser.add_argument('--' + command, action='store_true', help=help, dest=command)

args = parser.parse_args()

initLogging(args.actionlog_path)

# Leave a space in front of --url in case the user types cleos alone
# args.cleos += ' --url http://127.0.0.1:%d ' % args.http_port

logFile = open(args.log_path, 'a')

logFile.write('\n\n' + '*' * 80 + '\n\n\n')

background('killall nodeos keosd > /dev/null 2>&1')

with open(args.accounts_path) as f:
    a = json.load(f)
    if args.user_limit:
        del a['users'][args.user_limit:]
    if args.producer_limit:
        del a['producers'][args.producer_limit:]
    firstProducer = len(a['users'])
    numProducers = len(a['producers'])
    accounts = a['users'] + a['producers']

maxClients = numProducers + 10

haveCommand = False
for (flag, command, function, inAll, help) in commands:
    if getattr(args, command) or inAll and args.all:
        if function:
            haveCommand = True
            function()
if not haveCommand:
    print('boot.py: Tell me what to do. -a does almost everything. -h shows options.')

