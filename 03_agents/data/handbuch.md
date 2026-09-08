# Interner Leitfaden Cloud-Betrieb (Auszug)

## Deployment-Fenster
Produktive Deployments sind Dienstag bis Donnerstag zwischen 09:00 und 15:00 MEZ
erlaubt. Freitags gilt ein Deployment-Stopp, ausser fuer Sicherheits-Hotfixes.

## Freigaben
Jede Aenderung an der Produktionsumgebung braucht zwei Freigaben: eine fachliche
durch den Product Owner und eine technische durch den zustaendigen Platform Engineer.
Aenderungen an IAM-Rollen brauchen zusaetzlich die Freigabe der Security-Gruppe.

## Kostengrenzen
Ein Team darf pro Monat bis zu 5.000 EUR an Cloud-Kosten ohne Ruecksprache
verursachen. Ab 5.000 EUR ist ein Antrag im Kostenportal noetig, ab 20.000 EUR
entscheidet das Architecture Board.

## Modell-Nutzung
Fuer interne Prototypen sind alle Modelle im Foundry-Katalog freigegeben.
Fuer kundenfaehige Anwendungen sind nur Modelle mit EU-Datenresidenz erlaubt.
Personenbezogene Daten duerfen nie in Prompts fuer Modelle ausserhalb der EU.

## Incident-Prozess
Ein Sev-1 muss innerhalb von 15 Minuten im Incident-Kanal gemeldet werden.
Der Bereitschaftsdienst antwortet innerhalb von 30 Minuten. Ein Postmortem ist
innerhalb von fuenf Arbeitstagen faellig.
