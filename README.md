# Smart Sports Event Planning System

This project is a single-file Streamlit application in `app.py`. It uses SQLite for student registrations, organizer submissions, event allocations, and PDF certificates.

## Run locally

Use Python 3.10 or newer:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SPORTS_CERTIFICATE_ACCESS_CODE = "set-a-long-private-password"
$env:SPORTS_ADMIN_EMAIL = "admin@example.edu"
$env:SPORTS_ADMIN_PASSWORD = "set-a-different-long-password"
streamlit run app.py
```

The first configured admin account is created from `SPORTS_ADMIN_EMAIL` and `SPORTS_ADMIN_PASSWORD`. Staff must sign in to access the Organizer Inbox, Registration Records, Event Allocation, Tournament Scheduler, and Certificate Generation. Student QR links prefill the public registration form with the name, class/section, and EMIS number entered by the organizer. These details are carried in the URL, so share each QR only with its intended student or guardian. A local QR link only works on the same reachable network; different Wi-Fi networks require a public deployment.

## Deploy on Render

The included `render.yaml` configures a Render web service and a persistent disk for the SQLite database. Push this project to a private GitHub repository, create a Render Blueprint from that repository, and set `SPORTS_ADMIN_EMAIL`, `SPORTS_ADMIN_PASSWORD`, and `SPORTS_ADMIN_NAME` when prompted. Use a unique admin password; do not put secrets in `render.yaml` or source control. The Render hostname is detected automatically and used to create HTTPS registration links. The persistent disk requires a paid Render instance; do not use ephemeral storage for real registration data.

Keep the registration URL private to the intended participants and share the app only with trusted users. The public form accepts registration submissions; staff pages require admin or organizer accounts. Protect the Render account and database backups, and comply with applicable school/student-data policies before collecting real information.

By default, the app creates `sports_event.db` beside `app.py`. Set `SPORTS_DATABASE_PATH` to a persistent file path when hosting so registration records survive restarts. Do not commit the database if it contains real student details or identity documents.

## Included features

- Student registration QR is generated from the student's name, class/section, and EMIS number and opens the public registration form with those details prefilled.
- Individual/team registration tied to allocated event formats, duplicate EMIS/sport rejection, and organizer identity-document review status.
- Organizer inbox search and sport/status filters, pending/approved/rejected review with rejection reasons, summary counts, and filtered CSV export.
- Registration record listing and event allocation; outdoor events require a forecast check, and a high-risk forecast requires explicit organizer confirmation.
- Tournament Scheduler builds round-robin fixtures or knockout brackets, distributes matches across entered venues and round-based slots, reserves rest intervals, explains matches that do not fit, and saves schedules in SQLite.
- Password-gated sports-template PDF certificates for manually entered names or saved individual/team registrations, with award levels, event date and start time, and separate personalized PDFs for each name.
- Outdoor-event forecasts with temperature, rain probability, wind speed, and a sport-specific Weather Readiness Index, explained risk drivers, and organizer action plan.
- Sports Locations directory with indoor and outdoor Chennai and Chengalpattu sample listings, sport and area search, filters, nearby sorting, Google Maps links, and a demo booking-request form. Venue details and availability are illustrative, not live or verified.
- Help Center and sample event-allocation classifier.

The Decision Tree is trained on a small, hardcoded sample in `app.py`; it is a demonstration, not an evaluated production model. Home-page statistics and organizer contact details are also hardcoded examples.

Weather forecasts use the Open-Meteo geocoding and forecast APIs without an API key. Forecast lookup is available from the outdoor event allocation form for today through 15 days ahead. The Weather Readiness Index combines rain probability, wind, heat, and severe-weather codes with sport-specific sensitivities; its score, contributing signals, and recommended actions are shown to organizers. It is an explainable planning heuristic, not a safety guarantee or machine-learning prediction. The certificate artwork is stored at `assets/sports_certificate_template.png`; the name placeholder in the artwork is covered when generating a certificate.

The Tournament Scheduler creates a round-robin match for every competitor pair or a knockout bracket with byes and winner placeholders. Matches within a round are scheduled in parallel only when they use different venues and distinct competitors; subsequent slots include the configured rest interval. If the event window is too short, remaining fixtures are saved as unscheduled with an explanation. Knockout winner placeholders are planning fixtures and do not update automatically when match results are entered.

Staff-only pages require an admin or organizer account. The first admin is bootstrapped from `SPORTS_ADMIN_EMAIL` and `SPORTS_ADMIN_PASSWORD` (minimum 10 characters); additional organizer accounts currently need to be provisioned directly in the users database. Staff can manually compare each uploaded document with the player and school record; only a verified flag and timestamp are saved. This is not an Aadhaar/UIDAI verification integration, and the app must not be used to store Aadhaar numbers.

Certificate Generation has its own password, separate from the other pages. Configure `SPORTS_CERTIFICATE_ACCESS_CODE` in the server environment or Streamlit secrets (for example, `SPORTS_CERTIFICATE_ACCESS_CODE = "your-long-private-password"`), then restart the app. Do not commit the password. This password only restricts access to generating certificates; it does not verify participant eligibility or authenticate access to the other pages.

## Limitations and privacy

- Student registration is intentionally public so participants can open the form from a QR. Staff-only pages require staff sign-in. Uploaded documents are stored in SQLite without encryption at rest; use trusted hosting and protect persistent disks and backups.
- QR links include the student's name, class, and EMIS number for prefill. URLs may be retained in browser history and server logs; treat QR images and links as private. Local QR links require network reachability to the computer; Render deployments use their HTTPS hostname automatically. For other deployments, configure `APP_BASE_URL` with the externally reachable HTTPS URL.
- Organizer review status and rejection reasons are stored in the inbox. CSV exports contain personal registration data; restrict access and store exported files securely.
- Certificate generation requires the separate `SPORTS_CERTIFICATE_ACCESS_CODE`, but accepts manually entered names or saved registrations without document verification. Certificate IDs are printed on the PDF but are not stored in a verification database; treat generated certificates and downloads as public/unverified.
- This is a Streamlit app, not a static Netlify site. Static hosting does not run the Streamlit server or provide persistent SQLite storage. Use a Python-capable host with persistent storage and secure staff credentials.

## Dependencies

Install the packages listed in `requirements.txt`. QR image decoding through `pyzbar` may also require the native ZBar library on the target operating system.
