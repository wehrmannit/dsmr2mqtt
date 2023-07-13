# DSMR MQTT (FORKED FOR ENCRYPTED SMART READERS IN AUSTRIA)

This fork adds the encryption used by some power providers to `dsmr2mqtt`.

Basically all you need to do is to copy `config.rename.py` to `config.py` and adjust the settings for:
* MQTT Broker
* Provided keys from the power company. You might need to send them a polite email. They shouldn't have an issue with providing the keys.
* Test by running `python3 dsmr-mqtt.py`. If you can see the decrypted data, proceed.
****

* Run `cp systemd/dsmr-mqtt.service /etc/systemd/system/dsmr-mqtt-service`
* Run `systemctl enable power-mqtt.service` to execute the script

***
* Used P1 cable: https://www.amazon.de/dp/B07JW75BZ7?psc=1&ref=ppx_yo2ov_dt_b_product_details
* Script is running on a Raspi 3B+

***
HomeAssistant
- Create a Riemann sum integral sensor, set the MQTT sensor value ` sensor.momentane_wirkleistung_bezug_w` as entity, use `kilo` as metric and `hourly` as scale.
- Create an Utility Meter with the sensor created above and set `Meter reset cycle` to never.
- Go to https://my.home-assistant.io/redirect/config_energy/, press `Add Consumption` and add the created `Utility Meter` sensor.
- Done

# Original Text

MQTT client for Dutch Smart Meter (DSMR) - "Slimme Meter". Written in Python 3.x
 
Connect Smart Meter via a P1 USB cable to e.g. Raspberry Pi.

Application will continuously read DSMR meter and parse telegrams.
Parsed telegrams are send to MQTT broker.

Includes Home Assistant MQTT Auto Discovery.

In `dsmr50.py`, specify:
* Which messages to be parsed
* MQTT topics and tags
* MQTT broadcast frequency
* Auto discovery for Home Assistant

A typical MQTT message broadcasted
{"V1":226.0,"V2":232.0,"V3":229.0,"database":"dsmr","el_consumed":24488767.0,"el_returned":21190375.0,"p_consumed":1130.0,"p_generated":0.0,"serial":"33363137","timestamp":1642275125}

A virtual DSMR parameter is implemented (el_consumed and el_returned, which is sum of tarif1 and tarif2 (nacht/low en day/normal tariff)) - as some have a dual tarif meter, while energy company administratively considers this as a mono tarif meter.

## Usage:
* Copy `systemd/power-mqtt.service` to `/etc/systemd/system`
* Adapt path in `power-mqtt.service` to your install location (default: `/opt/iot/dsmr`)
* Copy `config.rename.py` to `config.py` and adapt for your configuration (minimal: mqtt ip, username, password)
* `sudo systemctl enable power-mqtt`
* `sudo systemctl start power-mqtt`

Use
http://mqtt-explorer.com/
to test &  inspect MQTT messages

A `test/dsmr.raw` simulation file is provided.
Set `PRODUCTION = False` in `config.py` to use the simulation file. No P1/serial connection is required.

## Requirements
* paho-mqtt
* pyserial
* python 3.x

Tested under Linux; there is no reason why it does not work under Windows.
Tested with DSMR v5.0 meter. For other DSMR versions, `dsmr50.py` needs to be adapted.
For all SMR specs, see [netbeheer](https://www.netbeheernederland.nl/dossiers/slimme-meter-15/documenten)

## Licence
GPL v3

## Versions
2.0.0 - 2.0.1
* Updated mqtt library
* Removed need for INFLUXDB label
* Added telegraf-dsmr.conf
* Added example (dsmr50_Stromnetz_Graz_Austria.py) for Austria dsmr (Stromnetz Graz, by karlkashofer)

1.0.13
* Add zero/non-zero check on data (as sometimes eg gas and power consumed values in influxdb became zero)

1.0.12
* Fix exit code (SUCCESS vs FAILURE)

1.0.2 - 1.0.4:
* Potential bug fix in parser
* Add MQTT last will/testament

1.0.0:
* Initial release
