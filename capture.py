#!/usr/bin/python3

import sys
import time
import subprocess
import json
import functools
from urllib.request import urlopen
from urllib.error import URLError

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

def wf(txt):
    try:
        with open("/home/pi/Pi/output.txt", "a", encoding="utf-8") as f:
            f.write(txt + "\n")
    except Exception as e:
        print(e)



def main(dev_name, api_url, capture_mac, conn_mac):
    tries = 0
    while True:
        wf('Starting...')
        subprocess.run(['killall', 'kismet'])
        time.sleep(20)
        subprocess.run(['killall', '-s', 'SIGKILL', 'kismet'])
        time.sleep(10)
        tries += 1

        wf('\nSetup networking...')
        capture_if_name = None
        conn_if_name = None

        for ifc in netifaces.interfaces():
            addr = list(map(lambda o: o['addr'], netifaces.ifaddresses(ifc)[netifaces.AF_LINK]))

            if(capture_mac in addr):
                capture_if_name = ifc

            if(conn_mac in addr):
                conn_if_name = ifc

        if(capture_if_name is None):
            wf("Capture if not found")
            raise Exception("Capture if not found")
        
        if(conn_if_name is None):
            wf("Connect if not found")
            raise Exception("Connect if not found")

        wf('Capture interface: {}'.format(capture_if_name))
        wf('Connect interface: {}'.format(conn_if_name))

        wf('\nStarting kismet...')
        command = ['bash', '-c', 'cd ~;kismet_server -c {} --daemonize'.format(capture_if_name)]
        wf('Run command: ' + ' '.join(command))
        subprocess.run(command)

        if not check_kismet_running():
            if tries > 5:
                break

            wf('Kismet not running, retrying... (try {} of {})\n\n'.format(tries, 5))
            continue

        wf('Kismet is running')

        while True:
            connected = check_connection(conn_if_name)
            try:
                data = {
                    'name': dev_name,
                    'ap': kismet_get_ap(),
                    'client_count': kismet_get_client_count(),
                    'devices': kismet_get_devices()
                }

                wf("sending data..")

                if(connected):
                    wf("Connected")
                    try:
                        url = api_url
                        response = requests.post(url, json=data)
                        wf("Data sent, response:")
                        wf(str(response))
                    except Exception as e:
                        wf("Exception:")
                        wf(str(e))
                else:
                    wf("Not connected") 
                    print(data)

                wf("Waiting 5 mins...")
                time.sleep(300)
            except KismetRest.KismetRequestException as e:
                break

        wf('\n\nExeption raised.. restarting kismet...\n\n')


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
    main("pi1", "https://api_url/", "9c:ef:d5:fd:8d:eb", "7c:dd:90:90:1b:ae")