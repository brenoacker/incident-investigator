# PostgreSQL for ticket persistence

The Ticketing SaaS will use PostgreSQL as the persistent source for tickets from the first business flow. This keeps the local environment aligned with the MVP architecture, allows tickets to survive process restarts and avoids a storage migration during the first ticket flows. The database runs as a local Docker Compose service.
