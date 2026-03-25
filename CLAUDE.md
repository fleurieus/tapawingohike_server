# TapawingoHike – Server (Django)

> Lees eerst `../CLAUDE.md` voor de gedeelde projectcontext.

## Communicatie
- Spreek Nederlands met de gebruiker
- Code, comments en commit messages in het Engels

## Stack (geverifieerd)
- **Framework**: Django 4.2.1 (Python 3.x)
- **Database**: SQLite (dev + prod)
- **Realtime**: Django Channels 3.0.4 / WebSocket (`ws://.../ws/app/`)
- **Frontend**: Django templates + Tailwind CSS + HTMX
- **Kaarten**: Google Maps API (backoffice)
- **State**: geen REST API – alles via WebSocket

## Stap 1 – Verken de codebase (altijd eerst doen)
Voordat je iets aanpast, voer uit en lees:
```bash
# Overzicht structuur
find . -name "*.py" | grep -v __pycache__ | sort
cat requirements.txt          # of requirements/*.txt
cat manage.py
ls */models.py                # alle modellen
ls */urls.py                  # alle URL configs
ls */serializers.py 2>/dev/null
ls */views.py
```
Beschrijf je bevindingen beknopt voordat je begint.

## Afgeronde taken
1. ~~**Dockerizen**~~ – Dockerfile, docker-compose.yml, entrypoint.sh, Tailwind CSS pipeline
2. ~~**E-mail aanmelden voor event**~~ – twee modi: snel (naam+email→code) en uitgebreid
   (volledig formulier→bevestigingsmail, handmatige activatie). Commit c81ffdf.
3. ~~**Bundle model**~~ – `Bundle` model + FK op RoutePart/TeamRoutePart, bundel-aware
   `get_next_open_routepart_formatted()`, backoffice CRUD UI. Migratie `0010_add_bundle_model`.
4. ~~**Route datum + locatielogs filteren**~~ – Optioneel `date` DateField op Route. Live map
   filtert locatielogs op route-datum (fallback: vandaag). Datumkiezer in route-formulier,
   datum-kolom in routes-lijst. Migratie `0015_add_route_date`.

## Kernmodellen (geverifieerd)
```
Organization → Event → Edition
                           ├→ Route → Bundle (nieuw)
                           │         → RoutePart (→ bundle FK, nullable)
                           │           → Destination
                           └→ Team → TeamRoutePart (→ bundle FK, nullable)
                                      → Destination
```

## WebSocket endpoints (geverifieerd)
- `authenticate` – team login met authStr
- `newLocation` – app vraagt volgend routedeel (of bundel)
- `destinationConfirmed` – app bevestigt checkpoint bereikt
- `updateLocation` – app stuurt GPS-positie
- `undoCompletion` – app maakt laatste voltooiing ongedaan

## Actieve taken
Geen server-specifieke taken op dit moment. Zie `../CLAUDE.md` voor de app-prioriteiten.

## Conventies in deze codebase (verifieer bij verkenning)
- App-namen en URL prefixes
- Authenticatie systeem (JWT? Session? Token?)
- Bestaande test-setup (`pytest` of `unittest`?)
- Static/media files configuratie

## Veelgebruikte commando's
```bash
python manage.py runserver
python manage.py makemigrations
python manage.py migrate
python manage.py shell
python manage.py test
```
Na dockerizen:
```bash
docker-compose up --build
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```
