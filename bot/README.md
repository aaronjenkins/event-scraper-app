sudo cp bot.service /etc/systemd/system/
sudo cp bot.timer   /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable bot.timer
sudo systemctl start bot.timer

sudo systemctl status bot.timer    # check timer status
sudo systemctl status bot.service  # check last service run
systemctl list-timers --all                  # see all timers + next run time
