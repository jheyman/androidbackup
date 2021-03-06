#!/usr/bin/python
import os
import sys
import subprocess
import time
import logging
import logging.handlers
from ConfigParser import SafeConfigParser

BACKUP_BASEDIR = "/mnt/remotebackup"

class ADBHelper(object):

	def command(self, cmd):
		logger.info("Executing command [%s]" % cmd)

		pipes = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		std_out, std_err = pipes.communicate()

		if pipes.returncode != 0:
		    logger.info("ERROR while executing cmd [%s]: code=%s, stderr=%s" % (cmd, pipes.returncode, std_err.strip()))

		# small delay to let the (adb) command be processed by the device
		time.sleep(0.5)

		return std_out

	def adb_command(self, command, deviceId=""):
		if (deviceId is not ""):
			target = '-s %s' % deviceId
		else:
			target = ""
		
		cmd = '/home/pi/androidbackup/adb %s %s' % (target,command)
		return self.command(cmd)

	def list_devices(self):
		result = self.adb_command("devices")
		devices = result.partition('List of devices attached \n')[2].replace('\n', '').split('\tdevice')
		return [device for device in devices if len(device) > 2]

	def get_model(self, deviceId):
		return self.adb_command("shell getprop ro.product.model", deviceId).rstrip()

	def get_orientation(self, deviceId=""):
		result = self.adb_command("shell dumpsys input | grep -i SurfaceOrientation", deviceId)
		
		if len(result.split(":")) >= 2:
			orientation = result.split(":")[1][1].lstrip().rstrip()
		else:
			return "error (txt=%s)"%result

		if (orientation == "0"):
			return "portrait"
		elif(orientation == "2"):
			return "reverse_portrait"
		elif(orientation == "1"):
			return "landscape"
		elif(orientation =="3"):
			return "reversed_landscape"
		else:
			return "unknown (%s)"%orientation

	def is_screen_off(self, deviceId=""):
		result = self.adb_command("shell dumpsys input_method | grep 'mScreenOn\|mInteractive'", deviceId)
		if ("mScreenOn=false" in result) or ("mInteractive=false" in result) :
			return True
		elif ("mScreenOn=true" in result) or ("mInteractive=true" in result):
			return False
		else:
			logger.info("Cannot determine screen status, returned string [%s] " % result)
			return False

	def launch_contacts_app(self, deviceId=""):
		#self.adb_command("shell am start -n com.android.contacts/com.android.contacts.DialtactsContactsEntryActivity", deviceId)
		# The statement above does not work on Android 8.0 anymore. The following seems to work on all versions 
		self.adb_command("shell am start -a android.intent.action.VIEW content://contacts/people/", deviceId)
   
	def tap(self, x, y, deviceId=""):
		# for debug purposes
		#self.screenshot("before_touch_%d_%d_%s.png" % (x,y,deviceId), deviceId)

		cmd = "shell input tap %d %d" % (x,y)
		self.adb_command(cmd, deviceId)

	def swipe(self, x1, y1, x2, y2, deviceId=""):
		# for debug purposes
		#self.screenshot("before_swipe_%d_%d_%d_%d%s.png" % (x1,y1,x2,y2,deviceId), deviceId)

		cmd = "shell input swipe %d %d %d %d 1000" % (x1,y1,x2,y2)
		self.adb_command(cmd, deviceId)

	def home(self, deviceId=""):
		logger.info("Remotely pushing HOME button")
		self.adb_command("shell input keyevent 3",deviceId)

	def menu(self, deviceId=""):
		logger.info("Remotely pushing MENU button")
		self.adb_command("shell input keyevent 82",deviceId)

	def delete_file(self, file, deviceId=""):
		self.adb_command("shell rm %s" %file, deviceId)

	def get_file(self, remote_file, local_file="", deviceId=""):
		self.adb_command("pull %s %s" %(remote_file, local_file), deviceId)

	def send_file(self, local_file, remote_file, deviceId=""):
		self.adb_command("push %s %s" %(local_file, remote_file), deviceId)

	def start_rsync(self, deviceId=""):
		self.adb_command("shell \'/sdcard/rsync.bin --daemon --config=/sdcard/rsyncd.conf --log-file=/data/local/tmp/foo &\'", deviceId)

	def unlock(self, passcode, deviceId=""):
		logger.info("Unlocking device %s" % deviceId)
		# send passcode
		self.adb_command("shell input text %s" % passcode, deviceId)
		self.ok(deviceId)

	def ok(self, deviceId=""):
		logger.info("Remotely pushing OK button")
		self.adb_command("shell input keyevent 66", deviceId)

	def power(self, deviceId=""):
		logger.info("Remotely pushing POWER button")
		self.adb_command("shell input keyevent 26", deviceId)

	def start_rsync_daemon(self, deviceId=""):
		self.send_file("rsync.bin", "/data/local/tmp/rsync", deviceId)
		self.send_file("rsyncd.conf", "/data/local/tmp", deviceId)
		self.adb_command("shell chmod 755 /data/local/tmp/rsync", deviceId)
		self.adb_command("shell \'/data/local/tmp/rsync --daemon --config=/data/local/tmp/rsyncd.conf --log-file=/data/local/tmp/rsync.log; sleep 1\'", deviceId)
	
	def is_rsync_daemon_running(self, deviceId="", command=""):
		ret = self.adb_command("shell %s"%command, deviceId)
		if "rsync" in ret:
			return True
		else:
			return False

	def kill_rsync(self, deviceId="", command=""):
		ret = self.adb_command("shell %s"%command, deviceId)
		if "rsync" in ret:
			pid = ret.split()[1]
			logger.info("Killing rsync process(%s)"%pid)
			self.adb_command("shell kill %s" % pid, deviceId)

	def sync_folder(self, remote_folder, local_folder, deviceId=""):
		self.adb_command("forward tcp:6010 tcp:1873", deviceId)
		self.command("rsync -az rsync://localhost:6010/root%s %s" % (remote_folder, local_folder))

	def screenshot(self, filename, deviceId=""):
		self.adb_command("shell screencap -p | perl -pe \'s/\\x0D\\x0A/\\x0A/g\' > %s" % filename, deviceId)

###########################
# PERSONAL CONFIG FILE READ
###########################

parser = SafeConfigParser()
parser.read('androidbackup.ini')

# Read path to log file
LOG_FILENAME = parser.get('config', 'log_filename')

#################
#  LOGGING SETUP
#################
LOG_LEVEL = logging.INFO  # Could be e.g. "DEBUG" or "WARNING"

# Configure logging to log to a file, making a new file at midnight and keeping the last 3 day's data
# Give the logger a unique name (good practice)
logger = logging.getLogger(__name__)
# Set the log level to LOG_LEVEL
logger.setLevel(LOG_LEVEL)
# Make a handler that writes to a file, making a new file at midnight and keeping 3 backups
handler = logging.handlers.TimedRotatingFileHandler(LOG_FILENAME, when="midnight", backupCount=3)
# Format each log message like this
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
# Attach the formatter to the handler
handler.setFormatter(formatter)
# Attach the handler to the logger
logger.addHandler(handler)

# Make a class we can use to capture stdout and sterr in the log
class MyLogger(object):
	def __init__(self, logger, level):
		"""Needs a logger and a logger level."""
		self.logger = logger
		self.level = level

	def write(self, message):
		# Only log if there is a message (not just a new line)
		if message.rstrip() != "":
			self.logger.log(self.level, message.rstrip())

# Replace stdout with logging to file at INFO level
sys.stdout = MyLogger(logger, logging.INFO)
# Replace stderr with logging to file at ERROR level
sys.stderr = MyLogger(logger, logging.ERROR)

logger.info('-----------------------')
logger.info('Starting android backup')
logger.info('-----------------------')

adb = ADBHelper()

devices = adb.list_devices()
logger.info("Detected devices:" + str(devices))

for device in devices:

	device_name = parser.get("%s"%device, "device_name")
	if device_name =="":
		logger.info("----- Unknown device %s (%s), skipping -----" % (device,adb.get_model(device)))
		continue
	
	logger.info("----- Backing up device %s -----" % device_name)
	
	###############
	# Setup
	###############
	adb.start_rsync_daemon(device)
	
	# Let rsync daemon start in the background and then check it
	time.sleep(2)
	
	RSYNC_CHECK_COMMAND = parser.get("%s"%device, "rsync_check_command")

	ret = adb.is_rsync_daemon_running(device, RSYNC_CHECK_COMMAND)
	if not ret:
		logger.info("ERROR: rsync daemon not started")
		continue

	backup_path = BACKUP_BASEDIR + "/" + device_name

	if not os.path.exists(backup_path):
		logger.info("Creating backup dir %s" % backup_path)
		os.mkdir(backup_path)
	else:
		logger.info("Using backup dir %s" % backup_path)

	###############
	# Backup photos
	###############
	photos_backup_path = backup_path + "/photos"

	if not os.path.exists(photos_backup_path):
		logger.info("Creating photos backup dir %s" % photos_backup_path)
		os.mkdir(photos_backup_path)
	else:
		logger.info("Using photos backup dir %s" % photos_backup_path)

	backup_photos_internalSDCard = parser.getboolean("%s"%device, "backup_photos_internalSDCard")
	if backup_photos_internalSDCard:
		INTERNAL_SDCARD_PHOTOPATH = parser.get("%s"%device, "internal_sdcard_photopath")
		logger.info("Backup photos from internal SD Card %s"% INTERNAL_SDCARD_PHOTOPATH)
		adb.sync_folder(INTERNAL_SDCARD_PHOTOPATH,photos_backup_path, device)
	
	backup_photos_externalSDCard = parser.getboolean("%s"%device, "backup_photos_externalSDCard")
	if backup_photos_externalSDCard:
		EXTERNAL_SDCARD_PHOTOPATH = parser.get("%s"%device, "external_sdcard_photopath")
		logger.info("Backup photos from external SD Card %s" % EXTERNAL_SDCARD_PHOTOPATH)
		adb.sync_folder(EXTERNAL_SDCARD_PHOTOPATH,photos_backup_path, device)

	#################
	# Backup Contacts
	#################
	backup_contacts = parser.getboolean("%s"%device, "backup_contacts")
	if backup_contacts:
		contacts_backup_path = backup_path + "/contacts"

		if not os.path.exists(contacts_backup_path):
			logger.info("Creating contacts backup dir %s" % contacts_backup_path)
			os.mkdir(contacts_backup_path)
		else:
			logger.info("Using contacts backup dir %s" % contacts_backup_path)

		logger.info("Backing up to " + contacts_backup_path)

		if adb.is_screen_off(device):
			logger.info("Device %s screen is off, triggering power on" % device)
			adb.power(device)


		swipe_before_unlock = parser.getboolean("%s"%device, "swipe_before_unlock")

		if (swipe_before_unlock):
			swipe_gesture = parser.get("%s"%device, "swipe_gesture").split(";")
			adb.swipe(int(swipe_gesture[0]),int(swipe_gesture[1]),int(swipe_gesture[2]),int(swipe_gesture[3]),device)

		passcode = parser.get("%s"%device, "passcode")

		adb.unlock(passcode, device)

		adb.launch_contacts_app(device)

		CONTACTS_FILE_EXPORTPATH = parser.get("%s"%device, "contacts_file_exportpath")

		adb.delete_file(CONTACTS_FILE_EXPORTPATH, device)

		open_menu = parser.getboolean("%s"%device, "open_menu")

		if (open_menu):
			adb.menu(device)

		orient =  adb.get_orientation(device)
		logger.info("Orientation is " + orient)

		nb_steps = parser.getint("%s"%device, "contacts_nb_touch_steps")

		for i in range (1, nb_steps+1):
			coords = parser.get("%s"%device, "contacts_step%d_%s" % (i,orient)).split(";")

			# Two coords = TAP action at x,y
			if len(coords)==2:
				adb.tap(int(coords[0]),int(coords[1]),device)
			# Four coords = SWIPE action between x1,y1 and x2,y2
			elif len(coords)==4:
				adb.swipe(int(coords[0]),int(coords[1]),int(coords[2]),int(coords[3]),device)
			else:
				logger.error("wrong number of coords")

		time.sleep(10)
		adb.get_file(CONTACTS_FILE_EXPORTPATH, contacts_backup_path, device)
	else:
		logger.info("No Contacts to backup for this device")

	############
	# Clean-up
	############
	adb.home(device)
	adb.kill_rsync(device, RSYNC_CHECK_COMMAND)
