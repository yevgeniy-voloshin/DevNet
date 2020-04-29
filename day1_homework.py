#!/usr/bin/env python3
# """Module docstring."""

#Imports
from netmiko import ConnectHandler
import csv
import logging
import datetime
import multiprocessing as mp
import difflib
import filecmp
import sys
import os

#Module 'Global' variables
# file should contain a list of devices in format: hostname,ip,port,username,password,device_type
DEVICE_FILE_PATH = 'devices.csv'

# directory
BACKUP_DIR_PATH = 'CONFIGURATIONS'
NTP_SERVER = '192.168.1.1'
#NTP_SERVER = '194.190.168.1'

def enable_logging():
    # This function enables netmiko logging for reference

    logging.basicConfig(filename='test.log', level=logging.DEBUG)
    logger = logging.getLogger("netmiko")

def get_devices_from_file(device_file):
    # This function takes a CSV file with inventory and creates a python list of dictionaries out of it
    # Each disctionary contains information about a single device

    # creating empty structures
    device_list = list()
    device = dict()

    # reading a CSV file with ',' as a delimeter
    with open(device_file, 'r') as f:
        reader = csv.DictReader(f, delimiter=',')

        # every device represented by single row which is a dictionary object with keys equal to column names.
        for row in reader:
            device_list.append(row)

    print ("Got the device list from inventory")
    print('-*-' * 10)
    print ()

    # returning a list of dictionaries
    return device_list

def get_current_date_and_time():
    # This function returns the current date and time
    now = datetime.datetime.now()

    print("Got a timestamp")
    print('-*-' * 10)
    print()

    # Returning a formatted date string
    # Format: YYYYMMDD
    return now.strftime("%Y%m%d")

def connect_to_device(device):
    # This function opens a connection to the device using Netmiko
    # Requires a device dictionary as an input

    # Since there is a 'hostname' key, this dictionary can't be used as is
    connection = ConnectHandler(
        host = device['ip'],
        port = device['port'],
        username = device['username'],
        password=device['password'],
        device_type=device['device_type'],
        secret=device['secret']
    )

    #print ('Opened connection to '+device['ip'])
    #print('-*-' * 10)
    #print()

    # returns a "connection" object
    return connection

def disconnect_from_device(connection, hostname):
    #This function terminates the connection to the device

    connection.disconnect()
    #print ('Connection to device {} terminated'.format(hostname))

def get_backup_file_path(hostname,timestamp):
    # This function creates a backup file name (a string)
    # backup file path structure is hostname/hostname-yyyy_mm_dd-hh_mm

    # checking if BACKUP_DIR_PATH directory exists, creating it if not present
    if not os.path.exists(os.path.join(BACKUP_DIR_PATH)):
        os.mkdir(os.path.join(BACKUP_DIR_PATH))

    # checking if BACKUP_DIR_PATH/device directory exists, creating it if not present
    if not os.path.exists(os.path.join(BACKUP_DIR_PATH, hostname)):
        os.mkdir(os.path.join(BACKUP_DIR_PATH, hostname))

    # Merging a string to form a full backup file name
    backup_file_path = os.path.join(BACKUP_DIR_PATH, hostname, '{}-{}.txt'.format(hostname, timestamp))
    #print('Backup file path will be '+backup_file_path)
    #print('-*-' * 10)
    #print()

    # returning backup file path
    return backup_file_path

def create_backup(connection, backup_file_path, hostname):
    # This function pulls running configuration from a device and (over)writes it to the backup file
    # Requires connection object, backup file path and a device hostname as an input

    try:
        # sending a CLI command using Netmiko and printing an output
        connection.enable()
        output = connection.send_command('show running-config all')

        # creating a backup file and writing command output to it
        with open(backup_file_path, 'w') as file:
            file.write(output)
        #print("Backup of " + hostname + " is complete!")
        #print('-*-' * 10)
        #print()

        # if successfully done
        return True

    except Error:
        # if there was an error
        print('Error! Unable to backup device ' + hostname)
        return False

def check_cdp(connection, hostname):
    # This function check if CDP enable and count of neighbors
    try:
        # sending a CLI command using Netmiko and printing an output
        connection.enable()
        output = connection.send_command('show cdp')

        #
        if "not enabled" in output:
            result = "CDP OFF, 0 peers"
        else: 
            nbrcnt = 0
            output = connection.send_command('show cdp entry *')
            for row in output.split('\n'):
                if "Device ID: " in row:
                    nbrcnt += 1
            result = "CDP ON, {} peers".format(nbrcnt)

        return result

    except Error:
        # if there was an error
        print('Error! Unable to retrive CDP info from ' + hostname)
        return False

def check_ios(connection, hostname):
    # This function check IOS version + NPE or PE
    try:
        # sending a CLI command using Netmiko and printing an output
        connection.enable()
        output = connection.send_command('show version | i Cisco IOS Software')
        Type = output.strip().split(', ')[1].split()[0]
        if "NPE" in output.strip().split(', ')[1].split()[-1].upper():
            Payload = "NPE"
        else:
            Payload = "PE"
        IOSVersion = output.strip().split(', ')[2].split()[1]
        output = connection.send_command('show version | i of memory.')
        Model = output.strip().split()[1] 

        #
        return Type + " " + Model +"|"+ IOSVersion +"|"+ Payload

    except Error:
        # if there was an error
        print('Error! Unable to retrive CDP info from ' + hostname)
        return False

def check_ntp(connection, hostname):
    # This function configure TZ + NTP server + ping check
    try:
        # sending a CLI command using Netmiko and printing an output
        connection.enable()
        # explicitly configure GMT TZ 
        connection.send_config_set("clock timezone GMT 0 0")

        ping_ntp = connection.send_command("ping {}".format(NTP_SERVER))

        if "!" in ping_ntp.strip():
            connection.send_config_set("ntp server {}".format(NTP_SERVER))
        #else:
            # NTP Server not pingable, not configuring NTP, False!
            #return False
            #print("NOT PINGABLE")
        output = connection.send_command('show ntp status')
        if "Clock is synchronized" in output.strip():
            return "NTP in Sync"
        else:
            return "NTP not Sync"


    except Error:
        # if there was an error
        print('Error! Unable to retrive CDP info from ' + hostname)
        return False


def process_target(device,timestamp):
    # This function will be run by each of the processes in parallel
    # This function implements a logic for a single device using other functions defined above:
    #  - connects to the device,
    #  - gets a backup file name and a hostname for this device,
    #  - creates a backup for this device
    #  - check if CDP enable and count of neighbors
    #  - check IOS version + NPE or PE
    #  - configure TZ + NTP server + ping check
    #  - terminates connection
    # Requires connection object and a timestamp string as an input

    connection = connect_to_device(device)
    
    backup_file_path = get_backup_file_path(device['hostname'], timestamp)
    create_backup(connection, backup_file_path, device['hostname'])
    CDP = check_cdp(connection, device['hostname'])
    #print(device['hostname'] + ":" + CDP)
    IOS = check_ios(connection, device['hostname'])
    #print(device['hostname'] + ":" + str(IOS))
    NTP = check_ntp(connection, device['hostname'])
    #print(device['hostname'] + ":" + str(NTP))
    disconnect_from_device(connection, device['hostname'])
    print (device['hostname'] +"|"+ IOS +"|"+ CDP+"|"+ NTP) 


def main(*args):
    # This is a main function

    # Enable logs
    enable_logging()

    # getting the timestamp string
    timestamp = get_current_date_and_time()

    # getting a device list from the file in a python format
    device_list = get_devices_from_file(DEVICE_FILE_PATH)

    # creating a empty list
    processes=list()

    # Running workers to manage connections
    with mp.Pool(4) as pool:
        # Starting several processes...
        for device in device_list:
            processes.append(pool.apply_async(process_target, args=(device,timestamp)))
        # Waiting for results...
        for process in processes:
            process.get()


if __name__ == '__main__':
    # checking if we run independently
    _, *script_args = sys.argv
    
    # the execution starts here
    main(*script_args)
