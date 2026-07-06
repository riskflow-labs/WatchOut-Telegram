from app.api import accounts, auth, dashboard, intelligence, messages, notifications, rules, runs, system, targets

routers = [
    auth.router,
    accounts.router,
    targets.router,
    rules.router,
    messages.router,
    notifications.router,
    runs.router,
    dashboard.router,
    intelligence.router,
    system.router,
]
