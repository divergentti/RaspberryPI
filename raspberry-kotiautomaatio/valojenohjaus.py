#!/usr/bin/env python3
"""
Valojen varsinainen ohjaus tapahtuu mqtt-viesteillä, joita voivat lähettää esimerkiksi lähestymisanturit,
kännykän sovellus tai jokin muu IoT-laite.
Ulkotiloissa valoja on turha sytyttää, jos valoisuus riittää muutenkin. Tieto valoisuudesta saadaan mqtt-kanaviin
valoantureilla, mutta lisätieto auringon nousu- ja laskuajoista voi olla myös tarpeen.

Tämä scripti laskee auringon nousu- ja laskuajat ja lähettää mqtt-komennon valojen
päälle kytkemiseen tai sammuttamiseen.

Lisäksi tämä scripti tarkkailee tuleeko liikesensoreilta tietoa liikkeestä ja laittaa valot päälle mikäli
aurinko on jo laskenut ja ajastimella ylläpidetty aika on ylitetty. Liikesensorin mikropython koodin ESP32:lle
löydät githubistani Divergentti-nimellä.

MUUTTUJAT: parametrit.py-tiedostosta tuodaan tarvittavat muuttujat. Tähän scriptiin keskeisesti
vaikuttavat muuttujat ovat:

1. LIIKE_PAALLAPITO_AIKA määrittää miten pitkään valoja pidetään päällä liikkeen havaitsemisen jälkeen (Int sekunteja).
2. VALOT_POIS tarkoittaa ehdotonta aikaa, jolloin valot laitetaan pois (string TT:MM)
3. VALO_ENNAKKO_AIKA tarkoittaa aikaa jolloin valot sytytetään ennen auringonnousua (string TT:MM).
4. VALO_ENNAKKO_PAALLE on aika joka pidetään valoja päällä ennen VALO_ENNAKKO_AIKA loppumista mikäli aurinko laskenut (string TT:MM)

Ajat ovat paikallisaikaa (parametrit.py-tiedostossa).
Laskennassa hyödynnetään suntime-scriptiä, minkä voit asentaa komennolla:

pip3 install suntime

15.9.2020 Jari Hiltunen
"""

import paho.mqtt.client as mqtt  # mqtt kirjasto
import time
import datetime
from dateutil import tz
import logging
from suntime import Sun
from parametrit import LATITUDI, LONGITUDI, MQTTSERVERIPORTTI, MQTTSERVERI, MQTTKAYTTAJA, MQTTSALARI, \
    VARASTO_POHJOINEN_RELE1_MQTTAIHE_1, VARASTO_POHJOINEN_RELE2_MQTTAIHE_2, VALOT_POIS_KLO, \
    VALO_ENNAKKO_AIKA, LIIKETUNNISTIN_ETELA_1, LIIKE_PAALLAPITO_AIKA, VALO_ENNAKKO_PAALLE

logging.basicConfig(level=logging.ERROR)
logging.error('Virheet kirjataan lokiin')

''' Globaalit muuttujat ja liipaisimet '''
valot_paalla = False
aurinko_laskenut = False

''' Globaalit päivämäärämuuttujat'''
aikavyohyke = tz.tzlocal()
liiketta_havaittu_klo = datetime.datetime.now().astimezone(aikavyohyke)
liike_loppunut_klo = datetime.datetime.now().astimezone(aikavyohyke)
edellinen_virhe_klo = datetime.datetime.now().astimezone(aikavyohyke)
liiketta_havaittu = False


''' Laskentaobjektit - longitudin ja latitudin saat osoitteesi perusteella Google Mapsista '''
aurinko = Sun(LATITUDI, LONGITUDI)

''' mqtt-objektit - nimet näkyvät mqtt-palvelimen mosquitto-hakemiston logissa'''
mqttvalot = mqtt.Client("valojenohjaus-laskettu")  # mqtt objektin luominen, tulee olla uniikki nimi
mqttliiketieto = mqtt.Client("valojenohjaus-liiketieto")  # mqtt objektin luominen, tulee olla uniikki nimi


def mqttvalot_yhdista(mqttvalot, userdata, flags, rc):
    """ Yhdistetaan mqtt-brokeriin ja tilataan aiheet """
    mqttvalot.subscribe(VARASTO_POHJOINEN_RELE2_MQTTAIHE_2)  # tilaa aihe releelle 2


def mqttvalot_pura_yhteys(mqttvalot, userdata, rc=0):
    logging.debug("Yhteys purettu: " + str(rc))
    mqttvalot.loop_stop()


def mqttyhdistaliike(mqttliiketieto, userdata, flags, rc):
    """ Yhdistetaan mqtt-brokeriin ja tilataan aiheet """
    mqttliiketieto.subscribe(LIIKETUNNISTIN_ETELA_1)  # tilaa aihe liikkeelle


def mqttliike_pura_yhteys(mqttliiketieto, userdata, rc=0):
    logging.debug("Yhteys purettu: " + str(rc))
    mqttliiketieto.loop_stop()


def virhetila_kasittely(virhe, scripti):
    global edellinen_virhe_klo
    
    ''' Käsitellään virheet ja estetään esimerkiksi logitiedoston täyttyminen virheistä. 
    IN: virheen koodi, scriptin nimi str '''
    print ("Tapahtui virhe: %s \nScriptissä: %s" %(virhe, scripti))
    logging.error("Virhe: %s scriptissa %s"  %(virhe, scripti))
    uusi_virhe_klo = datetime.datetime.now().astimezone(aikavyohyke)
    
    ''' Erityinen tarkistus mqtt-yhteydelle '''
    if (scripti == "looppi") and (mqttliiketieto.is_connected() is False) or (mqttvalot.is_connected() is False):
                print("Yhteys mqtt ei ole toiminnassa %s" % datetime.datetime.now())
                ''' Alusettaan yhteydet uudelleen ja odotetaan hetki '''
                mqttliiketieto.disconnect()
                mqttvalot.disconnect()
                time.sleep(2)
                alustus()
    
    virhe_delta = uusi_virhe_klo - edellinen_virhe_klo
    
    
    if virhe_delta.total_seconds() < 5:
        ''' Virheitä tulee enemmän kuin yksi viidessä sekunnissa '''
        print ("Syntyy liikaa virheitä, lopetetaan scriptit!")
        logging.error("Syntyy liikaa virheitä, scriptin toiminta lopetettu klo: %s " % datetime.datetime.now().astimezone(aikavyohyke) )
        raise 
    else:
        edellinen_virhe_klo == uusi_virhe_klo     
  


def valojen_ohjaus(status):
    """ Status on joko 1 tai 0 riippuen siitä mitä releelle lähetetään """
    try:
        ''' mqtt-sanoma voisi olla esim. koti/ulko/etela/valaistus ja rele 1 tarkoittaa päällä '''
        mqttvalot.publish(VARASTO_POHJOINEN_RELE2_MQTTAIHE_2, payload=status, retain=True)
        if mqttvalot.is_connected():
            return True

    except AttributeError:
        pass

    except OSError:
        virhetila_kasittely(OSError, "valojen_ohjaus")
        mqttliiketieto.disconnect()
        mqttvalot.disconnect()
        return False


def mqttviestiliike(mqttliiketieto, userdata, message):
    global liiketta_havaittu_klo
    global liike_loppunut_klo
    global liiketta_havaittu

    """ Tarkastellaan josko liiketunnistimelta olisi tullut viestiä """

    viesti = int(message.payload)

    if viesti == 1:
        liiketta_havaittu = True
        liiketta_havaittu_klo = datetime.datetime.now()
        return True
    else:
        liiketta_havaittu = False
        liike_loppunut_klo = datetime.datetime.now()
        return False


def alustus():
    broker = MQTTSERVERI  # brokerin osoite
    port = MQTTSERVERIPORTTI

    try:
        ''' Liikesensorin tilatiedoille'''
        mqttliiketieto.username_pw_set(MQTTKAYTTAJA, MQTTSALARI)  # mqtt useri ja salari
        mqttliiketieto.connect(broker, port, keepalive=60, bind_address="")  # yhdista mqtt-brokeriin
        mqttliiketieto.on_connect = mqttyhdistaliike  # mita tehdaan kun yhdistetaan brokeriin
        mqttliiketieto.on_disconnect = mqttliike_pura_yhteys  # mita tehdaan kun yhteys lopetetaan
        mqttliiketieto.on_message = mqttviestiliike  # maarita mita tehdaan kun viesti saapuu
        mqttliiketieto.loop_start()

        ''' Valojen ohjaukselle '''
        mqttvalot.username_pw_set(MQTTKAYTTAJA, MQTTSALARI)  # mqtt useri ja salari
        mqttvalot.connect(broker, port, keepalive=60, bind_address="")  # yhdista mqtt-brokeriin
        mqttvalot.on_connect = mqttvalot_yhdista  # mita tehdaan kun yhdistetaan brokeriin
        mqttvalot.on_disconnect = mqttvalot_pura_yhteys
        mqttvalot.loop_start()

    except OSError:
        virhetila_kasittely(OSError, "alustus")
        return False

    return True


def ohjausluuppi():
    global aurinko_laskenut
    global valot_paalla
    global liiketta_havaittu_klo
    global liike_loppunut_klo
    global liiketta_havaittu
    pitoajalla = False
    liikeyllapitoajalla = False

    if alustus():
        pass
    else:
        print("Alustus ei onnistu!")
        raise

    ''' Päivämäärämuuttujien alustus'''
    valot_ohjattu_pois = datetime.datetime.now().astimezone(aikavyohyke)
    valot_ohjattu_paalle = datetime.datetime.now().astimezone(aikavyohyke)

    ''' Lähetettään komento valot pois varmuuden vuoksi'''
    valojen_ohjaus(0)

    ''' Testaamista varten, iteraattori esimerkiksi tunneille
    x = 18
    '''

    """ Suoritetaan looppia kunnes toiminta katkaistaan"""
    while True:
        ''' Loopataan ja odotellaan samalla mqtt-sanomia'''
        if (mqttliiketieto.is_connected() is False) or (mqttvalot.is_connected() is False):
            virhetila_kasittely("mqttyhteys", "looppi")
        
        ''' Huom! Palauttaa UTC-ajan ilman astitimezonea'''
        auringon_nousu_tanaan = aurinko.get_sunrise_time().astimezone(aikavyohyke)
        auringon_lasku_tanaan = aurinko.get_sunset_time().astimezone(aikavyohyke)
        auringon_nousu_huomenna = aurinko.get_sunrise_time().astimezone(aikavyohyke) + datetime.timedelta(days=1)
        # auringon_lasku_huomenna = aurinko.get_sunset_time().astimezone(aikavyohyke) + datetime.timedelta(days=1)

        ''' Mikäli käytät asetuksissa utc-aikaa, käytä alla olevaa riviä 
        ja muista vaihtaa datetime-kutusissa tzInfo=None'''
        aika_nyt = datetime.datetime.now().astimezone(aikavyohyke)

        ''' Testaamista varten 
        x = x + 1
        if x >= 24:
            x = 0
        aika_nyt = aika_nyt.replace(hour=x, minute=59)
        print (aika_nyt)
        '''

        ''' Kelloaika ennen auringonnousua jolloin valot tulisi laittaa päälle '''
        ennakko_tunnit, ennakko_minuutit = map(int, VALO_ENNAKKO_AIKA.split(':'))
        ennakko_arvo = aika_nyt.replace(hour=ennakko_tunnit, minute=ennakko_minuutit)

        ''' Valot_pois tarkoittaa aikaa jolloin valot tulee viimeistään sammuttaa päivänpituudesta riippumatta '''
        pois_tunnit, pois_minuutit = map(int, VALOT_POIS_KLO.split(':'))
        pois_arvo = aika_nyt.replace(hour=pois_tunnit, minute=pois_minuutit)

        ''' Auringon nousu tai laskulogiikka '''

        if (aika_nyt >= auringon_lasku_tanaan) and (aika_nyt < auringon_nousu_huomenna):
            aurinko_noussut = False
            aurinko_laskenut = True
        elif aika_nyt < auringon_nousu_tanaan:
            aurinko_noussut = False
            aurinko_laskenut = True
        else:
            aurinko_noussut = True
            aurinko_laskenut = False

        ''' Testataan ollaanko aamuyössä '''
        if (aika_nyt.hour >= 0) and (aika_nyt.hour <= auringon_nousu_tanaan.hour):
            aamuyossa = True
        else:
            aamuyossa = False

        ''' Valojen sytytys ja sammutuslogiikka'''

        ''' Jos aurinko on laskenut, sytytetään valot, jos ei olla yli sammutusajan ja eri vuorokaudella'''
        if (aurinko_laskenut is True) and (valot_paalla is False) and (aika_nyt < pois_arvo) and \
                (aamuyossa is False):
            valojen_ohjaus(1)
            valot_paalla = True
            pitoajalla = True
            valot_ohjattu_paalle = datetime.datetime.now().astimezone(aikavyohyke)
            print("Aurinko laskenut. Valot sytytetty klo: %s" % valot_ohjattu_paalle)


        ''' Aurinko laskenut ja valot päällä, mutta sammutusaika saavutettu '''
        if (aurinko_laskenut is True) and (valot_paalla is True) and (aika_nyt >= pois_arvo) and \
                (liikeyllapitoajalla is False):
            valojen_ohjaus(0)
            valot_paalla = False
            pitoajalla = False
            valot_ohjattu_pois = datetime.datetime.now().astimezone(aikavyohyke)
            valot_olivat_paalla = valot_ohjattu_pois - valot_ohjattu_paalle
            print("Valot sammutettu. Valot olivat päällä %s" % valot_olivat_paalla)

        ''' Tarkistetaan ollaanko ennakkoajalla, eli mistä mihin saakka valojen tulisi olla päällä '''
        poista_minuutteja = datetime.timedelta(minutes=VALO_ENNAKKO_PAALLE)
        valo_ennakko_klo = ennakko_arvo - poista_minuutteja

        if (valot_paalla is False) and (aurinko_laskenut is True) and (aika_nyt <= ennakko_arvo) \
                and (aika_nyt >= valo_ennakko_klo):
            valojen_ohjaus(1)
            valot_paalla = True
            pitoajalla = True
            valot_ohjattu_paalle = datetime.datetime.now().astimezone(aikavyohyke)
            print("Valot sytytetty ennakkoajan mukaisesti klo %s" % valot_ohjattu_paalle)

        ''' Jos aurinko noussut, sammutetaan valot '''
        if (aurinko_noussut is True) and (valot_paalla is True):
            valojen_ohjaus(0)
            valot_paalla = False
            pitoajalla = False
            valot_ohjattu_pois = datetime.datetime.now().astimezone(aikavyohyke)
            valot_olivat_paalla = valot_ohjattu_pois - valot_ohjattu_paalle
            print("Aurinko noussut. Valot sammutettu. Valot olivat päällä: %s" % valot_olivat_paalla)

        loppumisaika_delta = (datetime.datetime.now().astimezone(aikavyohyke) - liike_loppunut_klo.
                              astimezone(aikavyohyke)).total_seconds()

        ''' Liiketunnistuksen mukaan valojen sytytys ja sammutus ajan ylityttyä '''
        if (aurinko_laskenut is True) and (valot_paalla is False) and (liiketta_havaittu is True):
            valojen_ohjaus(1)
            valot_paalla = True
            liikeyllapitoajalla = True
            valot_ohjattu_paalle = datetime.datetime.now().astimezone(aikavyohyke)
            print("Valot sytytetty liiketunnistunnistuksen vuoksi klo %s" % valot_ohjattu_paalle)

        if (aurinko_laskenut is True) and (valot_paalla is True) and (liiketta_havaittu is False) and \
                (loppumisaika_delta > LIIKE_PAALLAPITO_AIKA) and (pitoajalla is False):
            valojen_ohjaus(0)
            print("Valot sammutettu liikkeen loppumisen vuoksi. Liikedelta: %s \n" % loppumisaika_delta)
            valot_paalla = False
            liikeyllapitoajalla = False
            valot_ohjattu_pois = datetime.datetime.now().astimezone(aikavyohyke)

        time.sleep(0.1)  # suoritetaan 0.1s valein


if __name__ == "__main__":
    ohjausluuppi()
