# TODO: Wereldkaart afmaken

Overzicht van wat er nog moet gebeuren aan `Wereld.svg`, gebaseerd op de antwoordenlijsten
(`Wereld_landen_en_hoofdsteden__antwoorden_2.docx` en `Wereld_overige__antwoorden_2.docx`)
en een controle van de huidige `<g class="question">`-elementen in de SVG.

## Status per onderdeel

| # | Onderdeel | Status | Actie nodig |
|---|---|---|---|
| 1 | Landen (51) | ✅ compleet | — |
| 2 | Hoofdsteden — Myanmar | ⚠️ fout | Vraag heet nu "Rangoon", moet "Nay Pyi Taw / Naypyidaw" zijn. Dit is niet alleen een tekstwijziging: Rangoon (Yangon) en Nay Pyi Taw liggen op andere plekken, dus het markeringspunt moet ook verplaatst worden naar de juiste locatie. |
| 3 | Hoofdsteden — Zuid-Afrika | ❌ ontbreekt | Vraag toevoegen voor Kaapstad/Pretoria/Bloemfontein (in het document als drie geldige antwoorden genoemd). |
| 4 | Vergrootglas Midden-Oosten (`<g id="nogDoen">`, 77 vormen) | 🚧 half af | Bevat een uitvergrote kopie van Turkije/Israël/Syrië/Jordanië/Irak/Iran/Saudi-Arabië (nummers 30-36 op de originele bronkaart), bedoeld om deze dicht-op-elkaar-liggende landen makkelijker aanklikbaar te maken. De vormen bestaan al, maar `class=""` matcht geen van de takken in `mapSession.fromSVG()` (`src/map.py`), dus de groep wordt momenteel volledig genegeerd en is nergens zichtbaar in de draaiende app. |
| 5 | `<g id="nogDoen2">` (2 vormen, `class="foreground"`) | 🚧 onduidelijk | Wordt wel getoond (valt onder de "foreground"-tak) maar heeft geen functie. Nagaan of dit bij de vergrootglas-inzet van punt 4 hoort of iets anders is. |
| 6 | Extra steden "overige" (17) | ❌ nog niet begonnen | Mumbai, Kolkata, Casablanca, Chicago, Hongkong/Xianggang, Istanbul, Lagos, Los Angeles, Mekka, Montréal, New York, Paramaribo, Rio de Janeiro, São Paulo, Shanghai, Singapore, Sydney. Nog geen vormen op de kaart. |
| 7 | Landstreken en gebergten (15) | ❌ nog niet begonnen | Alaska, Andes, Aruba, Curaçao, California, Florida, Hawaii, Himalaya, Java, Midden-Oosten, Molukken, Nederlandse Antillen, Rocky Mountains, Sahara, Siberië. Nog geen vormen op de kaart. |
| 8 | Werelddelen (7) | ❌ nog niet begonnen | Afrika, Noord-Amerika, Zuid-Amerika, Antarctica, Oceanië, Azië, Europa. Nog geen vormen op de kaart. |
| 9 | Wateren (15) | ❌ nog niet begonnen | Atlantische Oceaan, Amazone, Caribische Zee, Ganges, Huang He, Indische Oceaan, Chang Jiang, Mississippi, Nijl, Panamakanaal, Perzische Golf, Rode Zee, Grote Oceaan, Suezkanaal, Wolga/Volga. Nog geen vormen op de kaart. |

## Notities

- De front-end (`templates/index.html`) toont voor Wereld nu alleen "Landen" en "Steden" als
  aanvinkbare categorieën — dat klopt dus 1-op-1 met wat er in de SVG zit. Zodra categorie 6-9
  vormen krijgen, moet die lijst in `index.html` (rond regel 289, `category = ["Landen", "Steden"]`)
  worden uitgebreid, bijvoorbeeld met `"Steden"` (voor de losse steden), `"Gebieden"` en `"Wateren"`
  — vergelijkbaar met hoe dat al voor de Nederland-kaart is opgezet.
- Punten 6, 7, 8 en 9 vereisen nieuwe klikbare vormen op de juiste geografische locatie. Dat moet
  handmatig in een vector-editor (Inkscape) gebeuren door iemand die de kaart visueel kan
  controleren — dit kan niet betrouwbaar automatisch gegenereerd worden.
- Punten 2-5 zijn wijzigingen aan al bestaande elementen en zijn een goed startpunt om als eerste
  op te pakken.
