# Park & Collect für Home Assistant

Übermittelt Falschparker-Meldungen aus Home Assistant an [Park & Collect](https://www.park-collect.de).
Sie prüfen einen Fall in Home Assistant und geben ihn frei. Erst dann wird er gesendet. Park & Collect
prüft jede Meldung zusätzlich, eine Meldung löst also nie sofort eine Forderung aus.

## Voraussetzungen

- Park-&-Collect-Konto mit vollständigem Profil, unterschriebener Vollmacht und bestätigten AGB
- API-Schlüssel, zu erzeugen in der App unter **Profil → API-Zugang**
- Home Assistant, getestet mit Version 2026.10

## Installation

**Über HACS:** HACS öffnen, oben rechts das Menü wählen, **Benutzerdefinierte Repositories** öffnen,
`https://github.com/Park-Collect/ha-park-collect` als Typ **Integration** hinzufügen und
**Park & Collect** installieren. Danach Home Assistant neu starten.

**Von Hand:** Den Ordner `custom_components/park_collect` in Ihren Ordner `config/custom_components/`
kopieren und Home Assistant neu starten.

**Einrichten:** Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach
**Park & Collect** suchen und den API-Schlüssel eingeben.

## Was Sie danach haben

| Name | Art | Zweck |
|---|---|---|
| `select.park_collect_standard_parkplatz` | Auswahl | Alle Parkplätze Ihres Kontos. Gilt, wenn eine Meldung keinen Parkplatz nennt. |
| `sensor.park_collect_letzte_meldung` | Sensor | Stand der letzten Meldung, stündlich aktualisiert, mit Aktenzeichen als Attribut |
| `park_collect.submit_report` | Aktion | Meldung übermitteln |
| `park_collect_report_submitted` | Ereignis | Wird nach jeder angenommenen Meldung ausgelöst |

Die Entity-Namen richten sich nach der Sprache Ihrer Installation.

## Meldung übermitteln

```yaml
action: park_collect.submit_report
data:
  parkplatz_id: 5563
  kennzeichen: HN-AB 1234
  beginn: "2026-11-02T08:14:00+01:00"
  ende: "2026-11-02T09:02:00+01:00"
  grund: privatparkplatz
  abmahnen: false
  bilder:
    - pfad: /config/www/parken/einfahrt.jpg
      aufgenommen_am: "2026-11-02T08:14:03+01:00"
    - pfad: /config/www/parken/ausfahrt.jpg
      aufgenommen_am: "2026-11-02T09:01:48+01:00"
  vorgang_id: parkvorgang-20261102-0814
response_variable: meldung
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `parkplatz_id` | nein | ID des Parkplatzes. Ohne Angabe gilt der Standard-Parkplatz. |
| `kennzeichen` | ja | Deutsches Kennzeichen, von einem Menschen geprüft |
| `beginn` | ja | Beginn des Verstoßes. Ohne Zeitzone gilt die Zeitzone von Home Assistant. |
| `ende` | nein | Ende des Aufenthalts |
| `grund` | nein | Standard `privatparkplatz`, weitere: `kundenparkplatz`, `ausfahrt`, `parkplatz_blockiert`, `zugang`, `leistungsbetrug`, `ladesaeule` |
| `vertragsstrafe` | nein | Ganze Euro. Ohne Angabe gilt der Betrag des Parkplatzes. |
| `abmahnen` | nein | Ohne Angabe gilt die Einstellung des Parkplatzes. |
| `fahrzeug` | nein | Marke, Modell, Farbe |
| `bemerkung` | nein | Freitext, höchstens 2.000 Zeichen |
| `bilder` | ja | 1 bis 3 lokale JPEG- oder PNG-Dateien, je höchstens 10 MB. Als Pfad oder mit `pfad` und `aufgenommen_am`. Ohne Zeitangabe zählt das Dateidatum. |
| `vorgang_id` | nein | Eindeutige ID des Parkvorgangs |

Die Antwort enthält `id`, `aktenzeichen` und `status`.

**Bildordner freigeben.** Home Assistant darf nur freigegebene Ordner lesen. `/config/www` ist bereits
frei, andere Ordner tragen Sie in die `configuration.yaml` ein:

```yaml
homeassistant:
  allowlist_external_dirs:
    - /media/parken
```

## Doppelmeldungen

Dieselbe `vorgang_id` wird nur einmal gesendet. Ohne `vorgang_id` zählen Parkplatz, Kennzeichen und
Beginn. Ein erneuter Aufruf liefert die frühere Meldung mit `wiederholt: true`. Bei Verbindungsfehlern
wiederholt die Integration den Versand selbst, ohne dass eine zweite Meldung entsteht.

Bleibt nach einem Verbindungsabbruch unklar, ob die Meldung angekommen ist, kann ein späterer Aufruf
mit `Idempotency-Key mit anderem Inhalt verwendet` abgewiesen werden. Dann liegt die Meldung bereits
vor und Sie sehen sie in der App.

## Beispiel: Freigabe per Benachrichtigung

Diese Automation sendet erst, wenn Sie die Freigabe in einer Benachrichtigung der Home-Assistant-App
antippen. Die Helfer `input_text` und `input_datetime` stehen für Ihre eigene Logik, die Kennzeichen,
Zeiten und Bilder bereitstellt.

```yaml
alias: Falschparker freigeben
triggers:
  - trigger: event
    event_type: mobile_app_notification_action
    event_data:
      action: PARK_COLLECT_MELDEN
actions:
  - action: park_collect.submit_report
    data:
      parkplatz_id: "{{ states('input_number.parkplatz_id') | int }}"
      kennzeichen: "{{ states('input_text.parkvorgang_kennzeichen') }}"
      beginn: "{{ states('input_datetime.parkvorgang_beginn') }}"
      ende: "{{ states('input_datetime.parkvorgang_ende') }}"
      bilder:
        - /config/www/parken/einfahrt.jpg
        - /config/www/parken/ausfahrt.jpg
      vorgang_id: "{{ states('input_text.parkvorgang_id') }}"
```

Soll der Parkplatz von der Kamera abhängen, setzen Sie `parkplatz_id` je Kamera fest oder wählen ihn
per Vorlage aus. Die IDs sehen Sie in der Auswahl `Standard-Parkplatz`.

## Wichtig

- Melden Sie nur Fälle, die ein Mensch geprüft hat. Eine automatische Übermittlung ohne Prüfung ist
  nicht zulässig.
- Für den Betrieb Ihrer Kamera und die Erfassung von Kennzeichen sind Sie selbst verantwortlich.
- Fragen: support@park-collect.de
