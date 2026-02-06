@echo off
mkdir backups
copy company.db backups\company_backup_%date%.db
echo Бэкап создан!
pause