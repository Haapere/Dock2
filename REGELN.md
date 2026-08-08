# Regelwerk, Realitätscheck und Stufenplan zum Echtgeld

Du wolltest einen profitablen Trading-Bot, ein paar Regeln von dir und ein paar
Vorschläge von mir, Kriterien für die Auswahl der richtigen Werte — und dass ich
das Ganze auf Sinn und Realität prüfe, bevor irgendwann echtes Geld arbeitet.

Dieses Dokument ist die Antwort auf den Prüfteil. Es fängt mit der unbequemen
Einordnung an, weil alles andere darauf aufbaut.

---

## Teil 1: Die ehrliche Einordnung

### Was ich nicht liefern kann

Ich kann keinen Bot bauen, von dem ich weiß, dass er profitabel ist. Niemand
kann das, und wer es behauptet, verkauft etwas. Was ich bauen kann — und in
diesem Repository gebaut habe — ist ein Apparat, der **unprofitable Ideen
zuverlässig aussortiert**, bevor sie Geld kosten. Das ist weniger, als du
gefragt hast, aber es ist das Einzige, was ehrlich zu haben ist. Der Rest ist
Handwerk plus Geduld.

Der Grund ist keine Bescheidenheit, sondern Arithmetik. Ein Backtest ist eine
Messung mit sehr wenigen unabhängigen Datenpunkten. Zehn Jahre Tagesdaten sind
2.520 Kurse, aber eine Strategie mit Haltedauern von zwei Monaten macht darin
etwa 60 Trades. Aus 60 Beobachtungen lässt sich ein Vorteil grundsätzlich nicht
mit der Sicherheit nachweisen, die man bräuchte, um ihm Geld zu geben — schon
gar nicht, wenn vorher 200 Varianten durchprobiert wurden, um genau diese zu
finden.

### Der Befund, der alles andere überschattet

Beim Bauen habe ich das Prüfwerkzeug gegen künstliche Daten mit *bekanntem,
eingebautem* Vorteil getestet. Das Ergebnis ist die wichtigste Zahl in diesem
Dokument:

> Ich habe eine Kursreihe erzeugt, deren Tagesrenditen eine Autokorrelation von
> **0,18** haben — also einen enormen, direkt ausnutzbaren Momentum-Effekt. Echte
> Aktienmärkte liegen bei etwa 0,00 bis 0,05. Eine passende Strategie erreichte
> darauf ohne Kosten einen Sharpe von **0,86**. Mit realistischen Kosten von
> 0,15 % je Umschichtung: **Sharpe 0,13, praktisch null.** Die Break-Even-Kosten
> lagen bei 0,17 % — hauchdünn über den tatsächlichen 0,15 %.

Ein zehnfach übertriebener Vorteil, und die Transaktionskosten fressen ihn
trotzdem auf. Das ist die zentrale Lektion: **Bei einem Retail-Bot ist fast
immer die Kostenhürde die bindende Grenze, nicht die Signalqualität.** Wer nach
besseren Indikatoren sucht, optimiert die falsche Größe. Was zählt:

1. **Wie oft handelt die Strategie?** Jeder Trade kostet. Eine Strategie mit
   Haltedauern von Wochen hat gegenüber einer Tagesstrategie einen
   Kostenvorsprung, der praktisch nicht aufzuholen ist.
2. **Wie groß sind die Bewegungen, die sie einfängt?** Kosten von 0,3 % pro
   Rundlauf sind bei einem Wert mit 2 % Tagesschwankung eine Randnotiz und bei
   0,4 % Tagesschwankung tödlich. Genau das misst die `kostenhuerde` im Screener.
3. **Erst danach:** Wie gut ist das Signal?

### Was du noch dagegen rechnen musst

Zwei Posten fehlen in jedem Backtest dieses Werkzeugs und wirken beide gegen den
Bot:

**Steuern.** In Deutschland fallen auf realisierte Kursgewinne rund 26,4 %
Abgeltungssteuer plus Solidaritätszuschlag an (zzgl. Kirchensteuer), oberhalb
des Sparer-Pauschbetrags. Entscheidend ist nicht der Satz, sondern der
*Zeitpunkt*: Ein Bot realisiert Gewinne bei jedem Verkauf und versteuert sie
sofort. Kaufen-und-Halten verschiebt die Steuer um Jahrzehnte, und der nicht
abgeführte Betrag arbeitet weiter mit. Dieser Stundungsvorteil ist über lange
Zeiträume erheblich und geht komplett an den Bot verloren. Ich bin kein
Steuerberater und das ist keine Steuerberatung — rechne es mit deinem eigenen
Fall durch, bevor du Kapital bindest.

**Dein Verhalten.** Der häufigste Grund, warum ein funktionierender Bot Geld
verliert, ist, dass er im schlimmsten Moment abgeschaltet wird. Jede Strategie
hat Phasen von sechs bis achtzehn Monaten, in denen sie hinter dem Markt
zurückbleibt. Wer dann eingreift, realisiert genau den Drawdown und verpasst die
Erholung. Deshalb steht im Stufenplan unten, dass Abbruchkriterien **vorher**
schriftlich festgelegt werden.

### Was realistisch erreichbar ist

Kein Reichtum und keine Geldmaschine. Realistisch ist:

- Ein regelbasiertes System, das **definiertes Risiko** hat statt Bauchgefühl —
  das ist der handfeste Gewinn, und zwar unabhängig von der Rendite.
- Ein netto-Sharpe zwischen 0,4 und 0,8 wäre ein **gutes** Ergebnis. Ein breiter
  Aktienindex liegt langfristig bei etwa 0,4 bis 0,5, ohne jede Arbeit.
- Drawdowns von 15–25 % gehören dazu, auch wenn alles richtig läuft.
- Zeigt ein Backtest auf Tagesdaten einen Sharpe über 1,5, ist das fast immer
  ein Fehler im Code, ein Blick in die Zukunft oder Overfitting — nicht ein Fund.
  Diese Zahl ist ein Alarmsignal, kein Erfolg.

Der ehrlichste Vergleich: Wenn am Ende ein Sharpe von 0,5 herauskommt, hat der
Bot dasselbe erreicht wie ein weltweiter Index-ETF, nur mit mehr Arbeit,
Steuernachteil und Ausfallrisiko. Der Bot muss also **deutlich** besser sein, um
sich zu rechtfertigen — oder er muss etwas anderes leisten, etwa niedrigere
Drawdowns. Das ist der Maßstab, an dem die Prüfung ihn misst.

---

## Teil 2: Kriterien für die Werteauswahl

Das war deine konkrete Frage: nach welchen Kriterien man die richtigen Werte
findet. Sie stecken in `strategylab screen`. Es sind zwei Gruppen.

### Ausschlusskriterien (K.o.)

Wer hier durchfällt, ist für einen systematischen Bot ungeeignet — unabhängig
davon, wie gut ein Backtest aussieht.

| Kriterium | Grenze | Warum |
|---|---|---|
| **Kostenhürde** | ≤ 0,35 | Rundlaufkosten geteilt durch typische Tagesbewegung (ATR%). Der wichtigste Filter überhaupt, siehe Teil 1. Über 0,35 kostet jeder Trade mehr als ein Drittel einer Tagesbewegung. |
| **Historie** | ≥ 5 Jahre | Darunter gibt es zu wenige unabhängige Walk-Forward-Fenster für eine Validierung. |
| **Liquidität** | ≥ 5 Mio. Tagesumsatz | Darunter bewegt die eigene Order den Kurs; die Slippage-Annahme wird zur Fiktion. |
| **Kurs** | ≥ 5 € | Bei Pennystocks ist der prozentuale Spread unkalkulierbar. |
| **Volatilität** | 12 %–60 % p. a. | Unter 12 % ist zu wenig Bewegung, um Kosten zu verdienen. Über 60 % dominieren Sprünge, und Tagessignale kommen zu spät. |
| **Datenqualität** | < 15 % Nulltage | Viele Tage ohne Kursänderung heißen lückenhafte Daten oder Illiquidität. |
| **Gap-Risiko** | < 5 % Tage mit Sprung > 2×ATR | Wo häufig gesprungen wird, greifen Stops nicht zum gewünschten Kurs. |

### Charakterkriterien (welche Strategie passt)

Diese schließen nicht aus, sie **lenken die Strategieauswahl**. Eine
Trendfolge-Strategie auf einem seitwärts laufenden Wert zu optimieren erzeugt
zuverlässig Overfitting und nichts sonst.

- **`er_ratio`** — Efficiency Ratio relativ zum Zufallspfad. Über 1,25 heißt
  trendend (Trendfolge passt), unter 0,75 rückkehrend (Mean Reversion passt),
  dazwischen ist es Rauschen. Die Normierung ist wichtig: Ein reiner Zufallspfad
  hat eine absolute Efficiency Ratio von etwa 0,1, absolute Schwellen wie
  „über 0,3 ist Trend" sprechen deshalb nie an.
- **`autokorr`** — Autokorrelation der Tagesrenditen. Positiv deutet auf
  Momentum, negativ auf Rückkehr zum Mittelwert.

Beide Werte sind bei einem einzelnen Wert stark verrauscht. Ich habe das
gemessen: Über zwölf simulierte Zufallspfade streute `er_ratio` zwischen 0,59
und 1,17, obwohl keiner davon irgendeine Struktur hatte. Behandle die Einstufung
als Hinweis, nie als Befund.

### Die Regel gegen Selection Bias

Wer sein Universum auf der **vollen** Historie screent und dann auf derselben
Historie backtestet, hat schon verloren: Er wählt die Werte aus, die in der
Vergangenheit gut liefen, und misst dann, dass sie gut liefen. Deshalb hat
`screen` den Schalter `--until`. Für eine ehrliche Prüfung:

```bash
# Auswahl nur mit Daten bis Ende 2021 ...
strategylab screen --data data/*.csv --until 2021-12-31
# ... und die Strategie danach auf 2022+ prüfen.
```

### Konkreter Vorschlag für ein Startuniversum

Nicht Einzelaktien. Für einen ersten Bot sind **breite, liquide Index-ETFs oder
Indizes** die vernünftige Wahl, aus drei Gründen: Sie haben die niedrigsten
Spreads, kein Einzelwertrisiko (kein Bilanzskandal über Nacht), und ihre
Kursreihen sind frei von Survivorship Bias — eine Aktie, die es heute noch gibt,
ist eine Aktie, die nicht pleitegegangen ist, und ein Backtest auf heutigen
Indexmitgliedern überschätzt die Vergangenheit systematisch.

Sinnvoll sind **mindestens vier bis sechs Werte aus verschiedenen Ecken**:
verschiedene Regionen, gern auch verschiedene Anlageklassen (Aktien, Anleihen,
Gold, Rohstoffe). Der Grund steht in Teil 3 unter Diversifikation — fünf
Technologieaktien sind ein Wert in fünf Verkleidungen.

---

## Teil 3: Mein Regelvorschlag

Das ist meine Hälfte der Regeln. Sie sind bewusst langweilig. Trendfolge auf
einem gestreuten Universum ist die Strategiefamilie mit der längsten und
am besten dokumentierten Evidenz — nicht weil sie clever ist, sondern weil sie
wenig handelt und damit die Kostenhürde aus Teil 1 überspringt.

### Einstieg und Ausstieg

| Regel | Vorschlag | Begründung |
|---|---|---|
| Signal | Schneller SMA über langsamem SMA, z. B. 20/100 | Wenige Trades, robust, kaum Parameter. Zwei Parameter sind schwer zu überoptimieren, zwölf sind es nicht. |
| Übergeordneter Filter | Nur long, wenn Kurs über SMA200 | Hält aus Abwärtsmärkten heraus, wo Trendfolge am meisten verliert. |
| Richtung | Nur long | Short kostet Leihgebühren, hat unbegrenztes Verlustpotenzial und kämpft gegen die langfristige Aufwärtsdrift der Aktienmärkte. |
| Ausführung | Zum Schlusskurs, Signal vom Vortag | Genau das Modell des Backtesters. Kein Intraday, keine Hektik, einmal am Tag reicht. |
| Erwartete Handelsfrequenz | 2–6 Trades pro Jahr und Wert | Mehr heißt: Kosten prüfen. |

### Risikoregeln (die eigentlich wichtigen)

| Regel | Vorschlag | Begründung |
|---|---|---|
| Positionsgröße | Volatilitäts-Ziel 15 % p. a. | Wirksamster Einzelhebel gegen Überraschungen. Wird der Markt unruhig, sinkt die Position automatisch. |
| Hebel | Maximal 1,0 | Kein Fremdkapital. Hebel vervielfacht den Drawdown und damit die Wahrscheinlichkeit, im falschen Moment aufzugeben. |
| Stop-Loss | 3× ATR(14) | In ATR statt Prozent, damit der Stop bei ruhigen Werten eng und bei wilden weit sitzt. Unter 2× wird man vom normalen Rauschen ausgestoppt. |
| Notabschaltung | Bei 20 % Depot-Drawdown alles verkaufen, 20 Tage Pause | Versicherung für den Fall, dass der Vorteil wirklich verschwunden ist. Kostet Rendite bei Fehlalarm, verhindert den Totalverlust. |
| Toleranzband | 10 Prozentpunkte | Ohne Band schichtet die Vol-Steuerung täglich auf Rauschen um und verbrennt Gebühren. Gemessen: über 40 % weniger Umschlag. |
| Gewicht je Wert | Maximal 25 % | Kein Wert darf das Depot dominieren. Achtung: Bei vier Werten ist das Depot damit höchstens voll investiert, bei drei nur zu 75 %. Das ist Absicht. |
| Mindestordergröße | 250 € | Bei 5 € Gebühr sind 100 € Ordervolumen 5 % Kosten. Kleine Anpassungen kosten mehr, als die genauere Gewichtung wert ist. |

### Diversifikation — die Zahl, die man kennen muss

Bei *k* Werten mit gleichem Vorteil und durchschnittlicher Korrelation ρ sinkt
die Portfolio-Volatilität auf √(ρ + (1−ρ)/k) der Einzelvolatilität.

- 5 unkorrelierte Werte (ρ = 0): **55 % weniger Schwankung**, gleicher Ertrag —
  der Sharpe verdoppelt sich. Im Test dieses Repositories gemessen: 46,9 %.
- 5 Werte mit ρ = 0,8, wie unter Aktien desselben Marktes üblich: **nur 8 %**.

Diversifikation zahlt sich also ausschließlich aus, wenn die Werte wirklich
verschieden sind. `strategylab portfolio` gibt darum immer die
Korrelationsmatrix mit aus — damit du siehst, ob du gestreut hast oder es nur
glaubst.

### Was du entscheiden musst (deine Hälfte)

Diese Punkte kann ich nicht für dich festlegen, weil sie von deiner Lage
abhängen und nicht von der Statistik:

1. **Wie viel Geld darf komplett verloren gehen?** Nicht „wie viel will ich
   einsetzen", sondern der Betrag, dessen Totalverlust nichts in deinem Leben
   ändert. Alles andere ist zu viel.
2. **Welchen Drawdown hältst du wirklich durch?** Nicht in der Theorie — stell
   dir den Betrag in Euro vor, den 20 % deines Einsatzes ausmachen, und ob du
   ihn im vierten Monat in Folge im Minus noch aushältst. Danach richtet sich
   die Zielvolatilität.
3. **Welches Universum?** Wo hast du Zugang, welche Ordergebühren zahlst du
   tatsächlich bei deinem Broker (das ist der Eingabewert für die Kostenhürde)?
4. **Wie viel Zeit pro Woche?** Der Bot braucht einmal täglich fünf Minuten für
   Kursdaten und Orderprüfung. Ist das nicht dauerhaft realistisch, ist ein
   Sparplan die bessere Lösung — ohne Ironie.
5. **Deine Abbruchkriterien**, schriftlich, vor dem ersten Euro. Siehe Stufe 4.

---

## Teil 4: Die Prüfschwellen

`strategylab check` prüft neun Kriterien. Vier sind K.-o.-Kriterien: Reißt eines,
lautet das Urteil NO-GO, und der Bot verweigert die Ausgabe von Orders.

| Kriterium | Schwelle | Gewicht | Wogegen es schützt |
|---|---|---|---|
| Out-of-Sample-Sharpe | > 0,5 | K.o. | Overfitting. Ohne Walk-Forward-Raster gibt es keine Out-of-Sample-Schätzung, und das Urteil kann nie GO lauten. |
| Permutationstest p-Wert | < 0,05 | K.o. | Timing-Glück. Die Positionsserie wird zyklisch verschoben — gleiche Haltedauern, gleiche Exposition, nur die Ausrichtung zum Kurs ist zerstört. Ist die echte Strategie nicht besser als ihre zufällig getimten Zwillinge, war nichts dran. |
| Deflated Sharpe | > 0,95 | K.o. | Mehrfachtests. Wer 500 Varianten probiert, findet garantiert eine mit Sharpe 1,5, auch auf Rauschen. Die Latte steigt mit der Anzahl der Versuche. |
| Break-Even-Kosten | > 3× tatsächliche Kosten | K.o. | Die Kostenfalle aus Teil 1. Ohne Sicherheitsabstand kippt ein einziger weiter Spread die Strategie ins Minus. |
| Anzahl Trades | ≥ 30 | weich | Zu kleine Stichprobe; Trefferquote und Sharpe sind dann Rauschen. |
| Profitable WF-Fenster | ≥ 60 % | weich | Ergebnisse, die aus einer einzigen Glücksphase stammen. |
| Max. Drawdown (OOS) | < 25 % | weich | Was psychologisch nicht durchzuhalten ist, wird am tiefsten Punkt abgeschaltet. |
| Besser als Buy & Hold und > 0 | ja | weich | Der Existenzgrund. Schlägt der Bot einen ETF nicht, ist der ETF die bessere Wahl. |
| Parameter-Plateau | > 0,6 | weich | Zufallsspitzen. Funktionieren die Nachbarparameter nicht, war das Optimum ein Lotteriegewinn. |

**Wichtig zur Deflated Sharpe Ratio:** Der Parameter `--trials` soll die Zahl
*aller* je probierten Varianten sein, nicht nur die des letzten Rasters. Wer
zehn Strategien mit je 50 Kombinationen durchprobiert hat, muss 500 angeben.
Sich hier selbst zu belügen ist bequem und macht die ganze Prüfung wertlos —
es ist die einzige Stelle im Werkzeug, die auf deine Ehrlichkeit angewiesen ist.

**Erwarte NO-GO.** Beim Testen dieses Werkzeugs ist praktisch jede Kombination
aus Standardstrategie und Kursreihe durchgefallen. Das ist das korrekte
Verhalten, kein Defekt. Ein NO-GO hat dir gerade Geld gespart.

---

## Teil 5: Der Stufenplan zum Echtgeld

Keine Stufe wird übersprungen. Jede hat ein Abbruchkriterium, das **vorher**
feststeht.

### Stufe 0 — Daten (1 Tag)

```bash
strategylab data fetch --symbol aapl.us --out data/aapl.csv
```

Mindestens 8–10 Jahre, mindestens 6 Werte aus verschiedenen Ecken.
*Abbruch:* Weniger als 5 Jahre Historie verfügbar → dieser Wert fliegt raus.

### Stufe 1 — Werteauswahl (1 Tag)

```bash
strategylab screen --data data/*.csv --round-trip-cost 0.003 --until 2021-12-31
```

Setze `--round-trip-cost` auf die Kosten, die **dein** Broker dir wirklich
berechnet, inklusive Spread. Zu niedrig angesetzt ist die häufigste Ursache für
einen Bot, der im Backtest verdient und live verliert.
*Abbruch:* Weniger als 4 Werte bestehen → Universum erweitern, nicht die
Kriterien lockern.

### Stufe 2 — Realitätsprüfung (1–2 Tage)

```bash
strategylab check --data data/aapl.csv --strategy sma_cross \
  --grid "fast=10|20|30" "slow=100|150|200" \
  --train 750 --test 250 --trials 500 \
  --risk --save checks/aapl.json
```

*Abbruch:* NO-GO. Nicht die Schwellen anpassen, nicht „nur noch eine Variante"
probieren — jede weitere Variante erhöht `--trials` und senkt die Deflated
Sharpe Ratio. Wer hier zehnmal nachjustiert, hat am Ende garantiert Overfitting
und ein Protokoll, das es nicht mehr erkennt.

### Stufe 3 — Papertrading, mindestens 6 Monate

```bash
strategylab paper init --account paper.json --strategy sma_cross --params fast=20,slow=100
strategylab paper update --account paper.json --data data/aapl.csv   # täglich
```

Sechs Monate sind das Minimum, und zwar mit **mindestens 20 tatsächlichen
Trades** — sonst ist nichts beobachtet worden. Parallel dazu täglich
`strategylab bot signals` laufen lassen und die Orders mitschreiben, ohne sie
auszuführen. Ziel dieser Stufe ist nicht die Rendite, sondern zwei andere
Fragen: Läuft der Betrieb technisch stabil? Und hältst *du* das aus?

*Abbruch:* Forward-Ergebnis weicht stark vom Backtest ab (etwa halber Sharpe
oder schlechter) → zurück zu Stufe 2. Oder du hast dreimal in Versuchung
kommend eingegriffen → die Strategie passt nicht zu dir, unabhängig von den
Zahlen.

### Stufe 4 — Erstes echtes Geld, mindestens 6 Monate unverändert

Jetzt, und keinen Tag früher. Regeln:

- Betrag: der aus Teil 3 Punkt 1. Voller Verlust muss egal sein.
- **Schriftliche Abbruchkriterien vorher festlegen**, zum Beispiel: „Ich stoppe
  bei 25 % Drawdown oder wenn nach 6 Monaten der Sharpe unter 0 liegt." Datiert
  und aufgeschrieben, weil man solche Grenzen im Moment des Verlusts zuverlässig
  verschiebt.
- **Sechs Monate keine Parameteränderung.** Kein Nachjustieren, kein „diesmal
  ist es anders". Wer während des Laufs optimiert, hat keinen Test mehr, sondern
  ein Bauchgefühl mit Zahlen daneben.
- Orders manuell ausführen. `strategylab bot signals --orders-csv orders.csv`
  rechnet, du prüfst und tippst.

*Abbruch:* eines der schriftlichen Kriterien greift. Dann wirklich aufhören und
nicht verhandeln.

### Stufe 5 — Langsam skalieren

Erst nach 12 Monaten echtem Betrieb mit Ergebnissen im Rahmen der Erwartung. Und
zwar in beide Richtungen: Verdoppeln erst nach je 6 weiteren guten Monaten,
Halbieren bei Erreichen der halben Abbruchschwelle. Eine Skalierungsregel, die
nur nach oben zeigt, ist keine Regel.

---

## Teil 6: Was dieses Werkzeug nicht kann

Damit klar ist, wo die Grenzen liegen:

- **Kein Intraday.** Nur Tagesdaten, nur Schlusskurse. Der Stop-Loss kann
  Intraday-Verluste grundsätzlich nicht begrenzen — er wird am Tagestief erkannt,
  aber erst zum Schlusskurs umgesetzt.
- **Keine Orderausführung.** Bewusst. Ein Programm mit Depotzugriff kann bei
  einem Datenfehler in Minuten verlieren, was in Monaten verdient wurde.
- **Keine Fundamentaldaten, keine Nachrichten, keine Regimeprognose.**
- **Keine Survivorship-Bias-Korrektur.** Kursdaten von heute existierenden
  Werten überschätzen die Vergangenheit. Ein Grund mehr für Indizes statt
  Einzelaktien.
- **Keine Aktiensplit- und Dividendenprüfung.** Stooq-Daten sind meist
  angepasst, aber ungeprüft. Ein nicht angepasster Split sieht wie ein
  90-%-Absturz aus und löst falsche Signale aus.
- **Keine Garantie.** Alle Kennzahlen sind Messungen an der Vergangenheit.
  Auch ein GO bedeutet nur: Der gemessene Vorteil ist statistisch nicht als
  Zufall erklärbar. Nicht, dass er anhält.

Dies ist ein Analysewerkzeug und keine Anlageberatung.
