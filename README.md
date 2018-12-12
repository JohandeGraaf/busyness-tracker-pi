# busyness-tracker-pi

## Raspbian image
Raspbian Stretch with desktop  
Version: November 2018  
Release date: 2018-11-13  
Kernel version: 4.14  

## Setup Pi
```
sudo dpkg-reconfigure tzdata
sudo raspi-config
```
rasp9123 – Change user password  
Enable - Network > Predictable network interface names  
Enable – Interface options > SSH  
High – Overclock  
Expand filesystem – Advanced options  
```
sudo apt-get update
sudo apt-get upgrade
```
Reboot

## Install dependencies
```
sudo apt-get install build-essential git libmicrohttpd-dev zlib1g-dev libnl-3-dev libnl-genl-3-dev libcap-dev libpcap-dev libncurses5-dev libnm-dev libdw-dev libsqlite3-dev pkg-config libprotobuf-dev libprotobuf-c-dev protobuf-compiler protobuf-c-compiler libsensors4-dev python python3 python-setuptools python-protobuf python-requests g++ libusb-1.0 rng-tools
pip3 install click netifaces requests
```

## Install kismet
```
git clone https://github.com/kismetwireless/kismet.git
cd kismet
git checkout c094f2f3fd0d3104b7325935e6e0a02adcd299c5
./configure
make
sudo make suidinstall
sudo usermod -aG kismet $USER
newgrp kismet
```
Check that you are in the Kismet group with: groups

## Wi-Fi Settings
Create wpa_supplicant.conf in /etc/wpa_supplicant/wpa_supplicant.conf
```
wpa_passphrase "<SSID>" "<PASSWORD>" | sudo tee -a /etc/wpa_supplicant/wpa_supplicant.conf
```

## Install busyness-tracker
```
cd /home/pi
mkdir Pi
git clone https://github.com/JohandeGraaf/busyness-tracker-pi.git
```
Put correct details in capture.py, line:
```
main("pi1", "https://api_url/", "9c:ef:d5:fd:8d:eb", "7c:dd:90:90:1b:ae")
```

## Start capture.py
```
python3 capture.py
```
or add line in /etc/rc.local:
```
python3 /home/pi/Pi/capture.py 2>&1 &
```

## Structure of JSON send to api_url
```
{
	name: “pi1”,
	ap (ordered by age and signal strength, filtered by kismet type: “Wi-Fi AP”): [
		{
			name: <AP SSID (string)>
			type: <kismet device type (string)>,
			macAddress: <AP BSSID (string)>,
			signalStrength: <Signal strength measured in dBm (number)>,
			age: <millis since Last Seen (number)>,
			channel: <channel (number)>,
			signalToNoiseRatio <SNR in dBm (number)>: 
		},
		….
	],
	client_count: {
		(filtered by BSSID/MAC CID has local bit not set AND kismet type: “Wi-Fi Client”
		filters out devices with MAC address randomization enabled; 
		https://en.wikipedia.org/wiki/MAC_spoofing#MAC_Address_Randomization_in_WiFi)
		filtered_num_last_5_mins: (number),
		filtered_num_last_hour: (number),
    
		(filtered by kismet type: “Wi-Fi Client”, “Wi-Fi Bridged” OR “Wi-Fi Device”)
		num_clients_last_5_mins: (number),
		num_clients_last_hour: (number)
	},
	devices (last seen last hour): [
		{
			name: <dev broadcasted name, or dev mac/BSSID (string)>
			type: <kismet device type (string)>,
			macAddress: <dev mac/BSSID (string)>,
			signalStrength: <Signal strength measured in dBm (number)>,
			age: <millis since Last Seen (number)>,
			channel: <channel (number)>,
			signalToNoiseRatio <SNR in dBm (number)>:
			crypto <encryption type (Wi-Fi AP only) (string)>
		},
		….
	]
}
```
