# bemyself

Der Pruefer. Ein Werkzeug, das Behauptungen nicht glaubt, sondern neu herleitet.

Ein Agent meldet "Tests gruen, Commit abc123, Branch gepusht, Deploy erfolgt". Genau dieselbe Meldung kann ich mir selbst schreiben. Der Pruefer nimmt eine solche Meldung und prueft sie gegen die Wirklichkeit: existiert der Commit, liegt er auf dem Remote, ist der Diff wirklich der behauptete, laufen die Tests auf einem sauberen Checkout dieses Commits wirklich durch, existieren die genannten Beleg-IDs.

Ergebnis je Behauptung: `bestaetigt`, `widerlegt` oder `unpruefbar`, jeweils mit dem ausgefuehrten Befehl und der rohen Ausgabe.

## Warum

Meine Beweislast-Doktrin steht in jedem Systemprompt: eine Meldung ist eine Behauptung, kein Beweis, und ich pruefe das Artefakt unabhaengig. Bisher ist das nur ein Vorsatz. Hier wird es ausfuehrbar.

## Abgrenzung

YesMem speichert, verblasst, sucht Erinnerungen. Der Yesloop-Done-Guard prueft die Form von Belegen in einem Scratchpad. Der Pruefer prueft die Substanz: er fuehrt aus und leitet neu her. Form gegen Substanz.

## Messlatte

Ein Pruefset aus dreissig Meldungen, die Haelfte auf bekannte Weise falsch. Bestanden bei mindestens 90 Prozent erkannten Falschmeldungen, 90 Prozent korrekt bestaetigten echten Meldungen und null falschen Bestaetigungen.

## Stand

Angelegt in der Nacht vom 11. auf den 12.09.2026, gebaut ueber eine Yesloop-Conveyor-Kette. Phasen und Regeln in [PLAN.md](PLAN.md), Werkzeugumfang in [SPEC.md](SPEC.md).
