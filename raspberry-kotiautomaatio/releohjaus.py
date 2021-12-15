#!/usr/bin/env python3
"""
Relemoduleiden ohjaus scripti. Scripti lukee relepinnien mukaisia GPIO-portteja
ja sen mukaisesti ohjaa releen paalle tai pois. Huomioi releiden kytkennat, eli:
 NC = Normally Connected
 NO = Normally Open
jolloin arvo 1 voi olla siis joko rele auki tai kiinni kytkennasta riippuen.

Ohjelmakoodissa arvo 0 tarkoittaa sita, etta releelle tuodaan jannite.

19.7.2020 Jari Hiltunen
"""

import paho.mqtt.client as mqtt # mqtt kirjasto
import RPi.GPIO as GPIO
import time
import syslog  # Syslogiin kirjoittamista varten
from parametrit import VARASTO_POHJOINEN_RELE1_PINNI, VARASTO_POHJOINEN_RELE2_PINNI, \
    VARASTO_POHJOINEN_RELE3_PINNI, VARASTO_POHJOINEN_RELE4_PINNI,\
    VARASTO_POHJOINEN_RELE1_MQTTAIHE_1, VARASTO_POHJOINEN_RELE2_MQTTAIHE_2, VARASTO_POHJOINEN_RELE3_MQTTAIHE_3,\
    VARASTO_POHJOINEN_RELE4_MQTTAIHE_4, MQTTSERVERIPORTTI, MQTTSERVERI, MQTTKAYTTAJA, MQTTSALARI

def mqttyhdista(mqttasiakas, userdata, flags, rc):
    # print("Yhdistetty " + str(rc))
    """ Yhdistetaan mqtt-brokeriin ja tilataan aiheet """
    mqttasiakas.subscribe(VARASTO_POHJOINEN_RELE1_MQTTAIHE_1)  # tilaa aihe releelle 1
    mqttasiakas.subscribe(VARASTO_POHJOINEN_RELE2_MQTTAIHE_2)  # tilaa aihe releelle 2
    mqttasiakas.subscribe(VARASTO_POHJOINEN_RELE3_MQTTAIHE_3)  # tilaa aihe releelle 3
    mqttasiakas.subscribe(VARASTO_POHJOINEN_RELE4_MQTTAIHE_4)  # tilaa aihe releelle 4
    return

def mqttviesti(mqttasiakas, userdata, message):
    """ Looppia suoritetaan aina kun aiheeseen julkaistaan viesti
    Muista laittaa mqtt-julkaisuun Retained = True, muutoin rele vain
    kay kerran paalla ja nollautuu!
    """
    viesti = int(message.payload)
    if (viesti < 0) or (viesti > 1):
        print("Virheellinen arvo!")
        syslog.syslog("Virheellinen arvo kutsussa!")
        return False
    """ Releelle ja aiheelle 1 """
    if (message.topic == VARASTO_POHJOINEN_RELE1_MQTTAIHE_1):
        try:
            GPIO.output(VARASTO_POHJOINEN_RELE1_PINNI, viesti)
        except OSError:
            print("Virhe %d" %OSError)
            syslog.syslog("Rele 1 %s" % OSError)
            GPIO.cleanup()
            return False
    """ Releelle ja aiheelle 2 """
    if (message.topic == VARASTO_POHJOINEN_RELE2_MQTTAIHE_2):
        try:
            GPIO.output(VARASTO_POHJOINEN_RELE2_PINNI, viesti)
        except OSError:
            print("Virhe %d" %OSError)
            syslog.syslog("Rele 2 %s" % OSError)
            GPIO.cleanup()
            return False
    """ Releelle ja aiheelle 3 """
    if (message.topic == VARASTO_POHJOINEN_RELE3_MQTTAIHE_3):
        try:
            GPIO.output(VARASTO_POHJOINEN_RELE3_PINNI, viesti)
        except OSError:
            print("Virhe %d" %OSError)
            syslog.syslog("Rele 3 %s" % OSError)
            GPIO.cleanup()
            return False
    """ Releelle ja aiheelle 4 """
    if (message.topic == VARASTO_POHJOINEN_RELE4_MQTTAIHE_4):
        try:
            GPIO.output(VARASTO_POHJOINEN_RELE4_PINNI, viesti)
        except OSError:
            print("Virhe %d" %OSError)
            syslog.syslog("Rele 4 %s" % OSError)
            GPIO.cleanup()
            return False
    return  # mqttviesti


def relepaaluuppi():
    GPIO.setmode(GPIO.BCM)
    """  Releiden pinnien GPIO- alkuasetus, oletus alustus 0 """
    GPIO.setup(VARASTO_POHJOINEN_RELE1_PINNI, GPIO.OUT, initial=0)
    GPIO.setup(VARASTO_POHJOINEN_RELE2_PINNI, GPIO.OUT, initial=0)
    GPIO.setup(VARASTO_POHJOINEN_RELE3_PINNI, GPIO.OUT, initial=0)
    GPIO.setup(VARASTO_POHJOINEN_RELE4_PINNI, GPIO.OUT, initial=0)
    """ mqtt-objektin luominen """
    """ Tassa kaytetaan salaamatonta porttia ilman TLS:aa, vaihda tarvittaessa """
    broker = MQTTSERVERI  # brokerin osoite
    port = MQTTSERVERIPORTTI
    mqttasiakas = mqtt.Client("rele-broker")  # mqtt objektin luominen, tulla olla uniikki nimi
    mqttasiakas.username_pw_set(MQTTKAYTTAJA, MQTTSALARI)  # mqtt useri ja salari
    mqttasiakas.connect(broker, port, keepalive=60, bind_address="")  # yhdista mqtt-brokeriin
    mqttasiakas.on_connect = mqttyhdista  # mita tehdaan kun yhdistetaan brokeriin
    mqttasiakas.on_message = mqttviesti  # maarita mita tehdaan kun viesti saapuu
    """ Suoritetaan looppia kunnes toiminta katkaistaan"""
    try:
        while True:
            mqttasiakas.loop_forever()
            time.sleep(0.1)
    except KeyboardInterrupt:
        syslog.syslog("relescripti katkaistu kasin")
        GPIO.cleanup()
        pass

if __name__ == "__main__":
    relepaaluuppi()
