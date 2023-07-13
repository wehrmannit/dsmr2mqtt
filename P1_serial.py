"""
Read dsmr telgrams from P1 USB serial.


To test in bash the P1 usb connector:
raw -echo < /dev/ttyUSB0; cat -vt /dev/ttyUSB0



        This program is free software: you can redistribute it and/or modify
        it under the terms of the GNU General Public License as published by
        the Free Software Foundation, either version 3 of the License, or
        (at your option) any later version.

        This program is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of
        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
        GNU General Public License for more details.

        You should have received a copy of the GNU General Public License
        along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import serial
import threading
import time
import re
import binascii
import argparse


from Cryptodome.Cipher import AES
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import (Cipher, algorithms, modes)
from cryptography.exceptions import InvalidTag
import config as cfg

# Logging
import __main__
import logging
import os
script=os.path.basename(__main__.__file__)
script=os.path.splitext(script)[0]
logger = logging.getLogger(script + "." +  __name__)


class TaskReadSerial(threading.Thread):

  def __init__(self, trigger, stopper, telegram):
    """

    Args:
      :param threading.Event() trigger: signals that new telegram is available
      :param threading.Event() stopper: stops thread
      :param list() telegram: dsmr telegram
    """

    logger.debug(">>")
    super().__init__()
    self.__trigger = trigger
    self.__stopper = stopper
    self.__telegram = telegram
    self.__counter = 0
    self.STATE_IGNORING = 0
    # Start byte (hex "DB") has been detected.
    self.STATE_STARTED = 1
    # Length of system title has been read.
    self.STATE_HAS_SYSTEM_TITLE_LENGTH = 2
    # System title has been read.
    self.STATE_HAS_SYSTEM_TITLE = 3
    # Additional byte after the system title has been read.
    self.STATE_HAS_SYSTEM_TITLE_SUFFIX = 4
    # Length of remaining data has been read.
    self.STATE_HAS_DATA_LENGTH = 5
    # Additional byte after the remaining data length has been read.
    self.STATE_HAS_SEPARATOR = 6
    # Frame counter has been read.
    self.STATE_HAS_FRAME_COUNTER = 7
    # Payload has been read.
    self.STATE_HAS_PAYLOAD = 8
    # GCM tag has been read.
    self.STATE_HAS_GCM_TAG = 9
    # All input has been read. After this, we switch back to STATE_IGNORING and wait for a new start byte.
    self.STATE_DONE = 10
    # Initial empty values. These will be filled as content is read
    # and they will be reset each time we go back to the initial state.
    self._state = self.STATE_IGNORING
    self._buffer = ""
    self._buffer_length = 0
    self._next_state = 0
    self._system_title_length = 0
    self._system_title = b""
    self._data_length_bytes = b""  # length of "remaining data" in bytes
    self._data_length = 0  # length of "remaining data" as an integer
    self._frame_counter = b""
    self._payload = b""
    self._gcm_tag = b""
    self._args = {}

    self.__tty = serial.Serial()
    self.__tty.port = cfg.ser_port
    self.__tty.baudrate = cfg.ser_baudrate
    self.__tty.parity = serial.PARITY_NONE
    self.__tty.stopbits = serial.STOPBITS_ONE

    try:
      if cfg.PRODUCTION:
        self.__tty.open()
        logger.debug(f"serial {self.__tty.port} opened")
      else:
        self.__tty = open(cfg.SIMULATORFILE, 'rb')

    except Exception as e:
      logger.error(f"ReadSerial: {type(e).__name__}: {str(e)}")
      self.__stopper.set()
      raise ValueError('Cannot open P1 serial port', cfg.ser_port)


  def __del__(self):
    logger.debug(">>")


  def __preprocess(self):
    """
      Add a virtual dsmr entry, which is sum of tariff 1 and tariff 2

      "1-0:1.8.1" + "1-0:1.8.2" --> "1-0:1.8.3"
      "1-0:2.8.1" + "1-0:2.8.2" --> "1-0:2.8.3"

      1-0:1.8.1(016230.132*kWh)
      1-0:1.8.2(007449.542*kWh)
      1-0:2.8.1(005998.736*kWh)
      1-0:2.8.2(015098.938*kWh)

    Returns:
      None
    """

    e_consumed = 0.0
    e_returned = 0.0

    for element in self.__telegram:
      try:
        value = re.match(r"1-0:1\.8\.1\((\d{6}\.\d{3})\*kWh\)", element).group(1)
        e_consumed = e_consumed + float(value)
      except:
        pass

      try:
        value = re.match(r"1-0:1\.8\.2\((\d{6}\.\d{3})\*kWh\)", element).group(1)
        e_consumed = e_consumed + float(value)
      except:
        pass

      try:
        value = re.match(r"1-0:2\.8\.1\((\d{6}\.\d{3})\*kWh\)", element).group(1)
        e_returned = e_returned + float(value)
      except:
        pass

      try:
        value = re.match(r"1-0:2\.8\.2\((\d{6}\.\d{3})\*kWh\)", element).group(1)
        e_returned = e_returned + float(value)
      except:
        pass

    # Insert the vrrtual entries in the dsmr telegram
    e_consumed = "{0:10.3f}".format(e_consumed)
    line = f"1-0:1.8.3({e_consumed}*kWh)"
    self.__telegram.append(line)

    e_returned = "{0:10.3f}".format(e_returned)
    line = f"1-0:2.8.3({e_returned}*kWh)"
    self.__telegram.append(line)


  def __read_serial(self):

    try:
      raw_data = self.__tty.read()
    except Exception as e:
      print(e)
      return

    # Read and parse the stream from the serial port byte by byte.
    # This parsing works as a state machine (see the definitions in the __init__ method).
    # See also the official documentation on http://smarty.creos.net/wp-content/uploads/P1PortSpecification.pdf
    # For better human readability, we use the hexadecimal representation of the input.
    hex_input = binascii.hexlify(raw_data)

    # Initial state. Input is ignored until start byte is detected.
    if self._state == self.STATE_IGNORING:
      if hex_input == b'db':
        self._state = self.STATE_STARTED
        self._buffer = b""
        self._buffer_length = 1
        self._system_title_length = 0
        self._system_title = b""
        self._data_length = 0
        self._data_length_bytes = b""
        self._frame_counter = b""
        self._payload = b""
        self._gcm_tag = b""
      else:
        return

    # Start byte (hex "DB") has been detected.
    elif self._state == self.STATE_STARTED:
      self._state = self.STATE_HAS_SYSTEM_TITLE_LENGTH
      self._system_title_length = int(hex_input, 16)
      self._buffer_length = self._buffer_length + 1
      self._next_state = 2 + self._system_title_length  # start bytes + system title length

    # Length of system title has been read.
    elif self._state == self.STATE_HAS_SYSTEM_TITLE_LENGTH:
      if self._buffer_length > self._next_state:
        self._system_title += hex_input
        self._state = self.STATE_HAS_SYSTEM_TITLE
        self._next_state = self._next_state + 2  # read two more bytes
      else:
        self._system_title += hex_input

    # System title has been read.
    elif self._state == self.STATE_HAS_SYSTEM_TITLE:
      if hex_input == b'82':
        self._next_state = self._next_state + 1
        self._state = self.STATE_HAS_SYSTEM_TITLE_SUFFIX  # Ignore separator byte
      else:
        print("ERROR, expected 0x82 separator byte not found, dropping frame")
        self._state = self.STATE_IGNORING


    # Additional byte after the system title has been read.
    elif self._state == self.STATE_HAS_SYSTEM_TITLE_SUFFIX:
      if self._buffer_length > self._next_state:
        self._data_length_bytes += hex_input
        self._data_length = int(self._data_length_bytes, 16)
        self._state = self.STATE_HAS_DATA_LENGTH
      else:
        self._data_length_bytes += hex_input

    # Length of remaining data has been read.
    elif self._state == self.STATE_HAS_DATA_LENGTH:
      self._state = self.STATE_HAS_SEPARATOR  # Ignore separator byte
      self._next_state = self._next_state + 1 + 4  # separator byte + 4 bytes for framecounter

    # Additional byte after the remaining data length has been read.
    elif self._state == self.STATE_HAS_SEPARATOR:
      if self._buffer_length > self._next_state:
        self._frame_counter += hex_input
        self._state = self.STATE_HAS_FRAME_COUNTER
        self._next_state = self._next_state + self._data_length - 17
      else:
        self._frame_counter += hex_input

    # Frame counter has been read.
    elif self._state == self.STATE_HAS_FRAME_COUNTER:
      if self._buffer_length > self._next_state:
        self._payload += hex_input
        self._state = self.STATE_HAS_PAYLOAD
        self._next_state = self._next_state + 12
      else:
        self._payload += hex_input

    # Payload has been read.
    elif self._state == self.STATE_HAS_PAYLOAD:
      # All input has been read. After this, we switch back to STATE_IGNORING and wait for a new start byte.
      if self._buffer_length > self._next_state:
        self._gcm_tag += hex_input
        self._state = self.STATE_DONE
      else:
        self._gcm_tag += hex_input

    self._buffer += hex_input
    self._buffer_length = self._buffer_length + 1

    if self._state == self.STATE_DONE:
      # print(self._buffer)

      data = self.analyze()
      for line in data.splitlines():
        self.__telegram.append(line)
        print(line);

      self._state = self.STATE_IGNORING

      # do some magic on telegram
      #/self.__preprocess()

      # Trigger that new telegram is available for MQTT
      self.__trigger.set()
    logger.debug("<<")


    return


    # Once we have a full encrypted "telegram", put everything together for decryption.
  def analyze(self):

    key = binascii.unhexlify(cfg.DECRYPT_KEY)
    additional_data = binascii.unhexlify(cfg.DECRYPT_AAD)
    iv = binascii.unhexlify(self._system_title + self._frame_counter)
    payload = binascii.unhexlify(self._payload)
    gcm_tag = binascii.unhexlify(self._gcm_tag)

    decryption = self.decrypt(
      key,
      additional_data,
      iv,
      payload,
      gcm_tag
    )
    return decryption.decode('utf-8', errors='ignore')
  def run(self):
    parser = argparse.ArgumentParser()
    self._args = parser.parse_args()

    while True:
      self.__read_serial()

  def decrypt(self, key, additional_data, iv, payload, gcm_tag):
      cipher = AES.new(key, AES.MODE_GCM, iv, mac_len=12)
      cipher.update(additional_data)
      return cipher.decrypt(payload)