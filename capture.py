#!/usr/bin/python3

import sys
import time
import subprocess
import json
import functools
from urllib.request import urlopen
from urllib.error import URLError

import click
import netifaces
import requests
import KismetRest

kismet_uri = 'http://localhost:2501'

def check_kismet_running():
    for _ in range(10):
        time.sleep(30)
        try:
            kr = KismetRest.KismetConnector(kismet_uri)
            status = kr.system_status()
            if 'kismet.system.devices.count' in status.keys():
                return True
        except Exception as e:
            pass

    return False

def is_connected():
    try:
        urlopen('http://216.58.192.142', timeout=2)
        return True
    except URLError as e: 
        return False

def check_connection(conn_if_name):
    if(is_connected()):
        return True

    subprocess.run(['sudo', 'killall', 'wpa_supplicant'])
    time.sleep(2)
    subprocess.run(['sudo', 'ifconfig', conn_if_name, 'up'])
    time.sleep(2)
    subprocess.run(['sudo', 'wpa_supplicant', '-B', '-c', '/etc/wpa_supplicant/wpa_supplicant.conf', '-i', conn_if_name])
    time.sleep(2)
    subprocess.run(['sudo', 'wpa_cli', '-i', conn_if_name, 'reconfigure'])
    time.sleep(10)

    return is_connected()


@click.command()
@click.option('--dev_name', help='Device name')
@click.option('--api_url', help='API url to post captured data')
@click.option('--capture_mac', help='mac of capture card')
@click.option('--conn_mac', help='mac of card used to connect to wifi')
def main(dev_name, api_url, capture_mac, conn_mac):
    tries = 0
    while True:
        print('Starting...')
        subprocess.run(['killall', 'kismet'])
        time.sleep(10)
        subprocess.run(['killall', '-s', 'SIGKILL', 'kismet'])
        time.sleep(2)
        tries += 1

        print('\nSetup networking...')
        capture_if_name = None
        conn_if_name = None

        for ifc in netifaces.interfaces():
            addr = list(map(lambda o: o['addr'], netifaces.ifaddresses(ifc)[netifaces.AF_LINK]))

            if(capture_mac in addr):
                capture_if_name = ifc

            if(conn_mac in addr):
                conn_if_name = ifc

        if(capture_if_name is None):
            raise Exception("Capture if not found")
        
        if(conn_if_name is None):
            raise Exception("Connect if not found")

        print('Capture interface: {}'.format(capture_if_name))
        print('Connect interface: {}'.format(conn_if_name))

        print('\nStarting kismet...')
        command = ['bash', '-c', 'cd ~;kismet_server -c {} --daemonize'.format(capture_if_name)]
        print('Run command: ' + ' '.join(command))
        subprocess.run(command)

        if not check_kismet_running():
            if tries > 5:
                break

            print('Kismet not running, retrying... (try {} of {})\n\n'.format(tries, 5))
            continue

        print('Kismet is running')

        while True:
            connected = check_connection(conn_if_name)
            try:
                data = {
                    'name': dev_name,
                    'ap': kismet_get_ap(),
                    'client_count': kismet_get_client_count(),
                    'devices': kismet_get_devices()
                }

                print("sending data..")

                if(connected):
                    try:
                        url = api_url
                        response = requests.post(url, json=data)
                        print(response)
                    except Exception as e: 
                        print(e)
                else: 
                    print(data)

                print("Waiting 5 mins...")
                time.sleep(300)
            except KismetRest.KismetRequestException as e:
                break

        print('\n\nExeption raised.. restarting kismet...\n\n')


def kismet_output_filter(kismet_output, epoch_time):
    for entry in kismet_output:
        if 'age' in entry:
            entry['age'] = round(epoch_time - entry['age'])

    return kismet_output

def kismet_output_filter_mac(entry):
    mac = entry['macAddress']
    if len(mac) < 3:
        return False
    return int(mac[1:2], 16) & (1<<1) == 0

def kismet_get_ap():
    ap_fields = [
        ['kismet.device.base.name', 'name'],
        ['kismet.device.base.type', 'type'],
        ['kismet.device.base.macaddr', 'macAddress'],
        ['kismet.device.base.signal/kismet.common.signal.last_signal', 'signalStrength'],
        ['kismet.device.base.last_time', 'age'],
        ['kismet.device.base.channel', 'channel'],
        ['kismet.device.base.signal/kismet.common.signal.last_noise', 'signalToNoiseRatio']
    ]
    regex = [
        ['kismet.device.base.type', '^Wi-Fi AP$']
    ]

    kr = KismetRest.KismetConnector(kismet_uri)
    epoch_time = time.time()
    aps = kismet_output_filter(kr.smart_device_list(fields = ap_fields, regex = regex), epoch_time)
    aps = sorted(aps, key=functools.cmp_to_key(lambda x, y: x['age'] - y['age']))[:15]
    aps = sorted(aps, key=functools.cmp_to_key(lambda x, y: y['signalStrength'] - x['signalStrength']))[:6]

    return aps

def kismet_get_client_count():
    client_fields = [
        ['kismet.device.base.macaddr', 'macAddress'],
        ['kismet.device.base.type', 'type'],
        ['kismet.device.base.last_time', 'age']
    ]
    regex_filtered = [
        ['kismet.device.base.type', '^Wi-Fi Client$']
    ]
    regex_unfiltered = [
        ['kismet.device.base.type', '^Wi-Fi Client|Wi-Fi Bridged|Wi-Fi Device$']
    ]

    kr = KismetRest.KismetConnector(kismet_uri)
    epoch_time = time.time()

    return {
        'filtered_num_last_5_mins': len(list(filter(kismet_output_filter_mac, kismet_output_filter(kr.smart_device_list(fields = client_fields, regex = regex_filtered, ts = -300), epoch_time)))),
        'filtered_num_last_hour': len(list(filter(kismet_output_filter_mac, kismet_output_filter(kr.smart_device_list(fields = client_fields, regex = regex_filtered, ts = -3600), epoch_time)))),
        'num_clients_last_5_mins': len(kismet_output_filter(kr.smart_device_list(fields = client_fields, regex = regex_unfiltered, ts = -300), epoch_time)),
        'num_clients_last_hour': len(kismet_output_filter(kr.smart_device_list(fields = client_fields, regex = regex_unfiltered, ts = -3600), epoch_time))
    }

def kismet_get_devices():
    device_fields = [
        ['kismet.device.base.name', 'name'],
        ['kismet.device.base.type', 'type'],
        ['kismet.device.base.crypt', 'crypt'],
        ['kismet.device.base.signal/kismet.common.signal.last_signal', 'signalStrength'],
        ['kismet.device.base.signal/kismet.common.signal.last_noise', 'signalToNoiseRatio'],
        ['kismet.device.base.channel', 'channel'],
        ['kismet.device.base.last_time', 'age'],
        ['kismet.device.base.macaddr', 'macAddress']
    ]

    kr = KismetRest.KismetConnector(kismet_uri)
    epoch_time = time.time()
    devices = kismet_output_filter(kr.smart_device_list(fields = device_fields, ts = -3600), epoch_time)
    devices = sorted(devices, key=functools.cmp_to_key(lambda x, y: x['age'] - y['age']))
    return devices

if __name__ == '__main__':
    main()
