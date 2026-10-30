@echo off
rem ============================================================
rem  Stripe webhook forwarding for LOCAL development.
rem
rem  Usage:  stripe-listen.bat           start forwarding (Ctrl+C to stop)
rem          stripe-listen.bat check     only verify the setup, then exit
rem
rem  Why this file exists: plain "stripe listen" uses whichever account the
rem  CLI happens to be logged in to. That profile silently changes on re-login,
rem  account switching, or when the 90-day CLI key expires, and then events
rem  never reach this machine (payment succeeds, webhook never arrives).
rem  This script uses STRIPE_SECRET_KEY from .env.development instead, so it is
rem  always the same account Django talks to, regardless of CLI login state.
rem
rem  Keep this file ASCII-only. cmd re-reads batch files by byte offset, and
rem  multi-byte characters (e.g. Chinese) make it mis-parse lines after chcp.
rem ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "RC=0"

set "ENVFILE=.env.development"
if not exist "%ENVFILE%" (
    echo [ERROR] %ENVFILE% not found. Run this from the tjweb folder.
    set "RC=1"
    goto :done
)

rem Read the two values; %%~b strips surrounding double quotes.
set "SK="
set "WH="
for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b /c:"STRIPE_SECRET_KEY=" /c:"STRIPE_WEBHOOK_SECRET=" "%ENVFILE%"`) do (
    if "%%a"=="STRIPE_SECRET_KEY" set "SK=%%~b"
    if "%%a"=="STRIPE_WEBHOOK_SECRET" set "WH=%%~b"
)

if not defined SK (
    echo [ERROR] STRIPE_SECRET_KEY is missing from %ENVFILE%
    set "RC=1"
    goto :done
)
if /i not "!SK:~0,8!"=="sk_test_" (
    echo [ABORT] STRIPE_SECRET_KEY does not start with sk_test_.
    echo         This script is for test mode only, so live events are never
    echo         forwarded into a local machine by mistake.
    set "RC=1"
    goto :done
)

where stripe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] stripe CLI not found. Install it: winget install Stripe.StripeCli
    set "RC=1"
    goto :done
)

rem Ask Stripe for the signing secret of the account this key belongs to and
rem compare it with .env. If they differ, Django rejects every webhook with a
rem 400 signature error and nothing on screen says why.
set "LISTEN_SECRET="
for /f "delims=" %%s in ('stripe listen --api-key "!SK!" --print-secret 2^>nul') do set "LISTEN_SECRET=%%s"

if not defined LISTEN_SECRET (
    echo [ERROR] Could not get a signing secret. Check that STRIPE_SECRET_KEY is
    echo         valid and that you are online.
    set "RC=1"
    goto :done
)

if /i "!LISTEN_SECRET!"=="!WH!" (
    echo [OK] STRIPE_WEBHOOK_SECRET matches this account's signing secret.
) else (
    echo.
    echo [WARNING] STRIPE_WEBHOOK_SECRET does NOT match this account's signing secret.
    echo           Every webhook will be rejected with a signature error.
    echo           Set STRIPE_WEBHOOK_SECRET in %ENVFILE% to:
    echo.
    echo               !LISTEN_SECRET!
    echo.
    echo           then run: docker compose restart web
    echo.
    if /i "%~1"=="check" (
        set "RC=2"
        goto :done
    )
    echo           Forwarding will still start, but paid unlocks will NOT be granted.
    echo.
)

if /i "%~1"=="check" goto :done

echo Forwarding to http://localhost:8000/commerce/webhook/  (Ctrl+C to stop)
echo.
rem Newer CLI versions (1.4x+) refuse to start without --events; older ones forwarded
rem everything. Keep this list identical to the event types handled in
rem commerce/views.py stripe_webhook(), or new event types will be silently dropped.
stripe listen --api-key "!SK!" --events checkout.session.completed,customer.subscription.updated,customer.subscription.deleted,invoice.payment_succeeded --forward-to localhost:8000/commerce/webhook/
set "RC=!errorlevel!"

:done
endlocal & exit /b %RC%
