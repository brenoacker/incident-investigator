# PostgreSQL para persistência de tickets

O Ticketing SaaS usará PostgreSQL como fonte persistente dos tickets desde o primeiro fluxo de negócio. A escolha mantém o ambiente local alinhado à arquitetura do MVP, permite recuperar tickets após reinícios do processo e evita uma migração de armazenamento entre os primeiros tickets; o banco será executado como serviço local no Docker Compose.
