# Platsbanken Scraper

Det här projektet är ett enkelt Python skript som söker igenom annonser på Platsbanken och letar efter dina nyckelord.

Programmet öppnar en söksida från Arbetsförmedlingen, samlar annonslänkar från en eller flera resultatsidor, går in i varje annons och kontrollerar om något av dina nyckelord finns i texten. När en träff hittas sparas den i en textfil.

## Vad programmet gör

1. Öppnar en Platsbanken sök URL.
2. Samlar in annonslänkar från sökresultatet.
3. Går vidare till nästa sida om du har valt fler sidor.
4. Öppnar varje annons.
5. Letar efter dina nyckelord i annonsens innehåll.
6. Sparar träffar i formatet `Sökord | Företag | URL`.

## Krav

1. Python 3.10 eller nyare rekommenderas.
3. Playwright måste installeras tillsammans med Chromium.

## Installation

1. Öppna terminalen i projektmappen.

2. Installera Playwright:

```powershell
pip install playwright
```

3. Installera webbläsaren som Playwright använder:

```powershell
playwright install chromium
```

## Starta programmet

Kör skriptet med:

```powershell
python platsbanken_scraper.py
```

När programmet startar visas en enkel meny i terminalen.

## Så använder du programmet

1. Välj om du vill ändra nyckelord.
2. Välj om du vill ändra start URL till en egen Platsbanken sökning.
3. Välj om du vill ändra namn på utdatafilen.
4. Välj hur många sidor som ska skannas.
5. Starta scraping från menyn.

Standardvärden i programmet är:

1. Start URL för Jönköpings län.
2. Utdatafil: `matches.txt`
3. Antal sidor: `3`
4. Exempel på nyckelord: `developer`, `python`, `cybersecurity`, `nätverk`, `linux`

## Exempel på resultat

Om programmet hittar en match sparas en rad som kan se ut så här:

```text
python | Exempelbolaget AB | https://arbetsformedlingen.se/platsbanken/annonser/12345678
```

Om filen redan finns lägger programmet bara till nya rader som inte redan finns i filen.

## Start

1. Gå till Platsbanken i webbläsaren.
2. Skapa en sökning med de filter du vill använda.
3. Kopiera adressen från sökningen.
4. Klistra in adressen i programmet som start URL.
5. Ange dina nyckelord.
6. Kör skanningen.
7. Öppna resultatfilen och gå igenom träffarna.

## Filer i projektet

`platsbanken_scraper.py` innehåller hela programmet.

`matches.txt` skapas när programmet hittar träffar och sparar resultat.

## Att tänka på

1. Om Platsbanken ändrar sin webbplats kan delar av skriptet behöva uppdateras.
2. Om inga träffar hittas kan du testa andra nyckelord, fler sidor eller en annan sök URL.
3. Första körningen kan ta lite tid eftersom programmet går igenom annonserna en i taget.

## Sammanfattning

Det här projektet passar dig som vill automatiskt leta efter jobbannonser som innehåller vissa ord eller tekniker utan att själv öppna varje annons manuellt.
