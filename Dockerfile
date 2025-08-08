FROM postgres:17.5

# Instala pacotes necessários
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    postgresql-server-dev-all \
    python3.11 \
    python3-pip \
    postgresql-plpython3-17 \
    libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# Instala a ferramenta 'just'
RUN mkdir -p /usr/local/bin && \
    curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Clona os repositórios pgvector e pgai
WORKDIR /tmp
RUN git clone https://github.com/pgvector/pgvector.git
RUN git clone https://github.com/timescale/pgai.git --branch extension-0.6.0

# Compila e instala o pgvector
WORKDIR /tmp/pgvector
RUN make && make install

# Instala a extensão pgai usando 'just'
WORKDIR /tmp/pgai
RUN just ext install

# (REMOVIDO) pg_search via RPM (incompatível com base Debian)
# # WORKDIR /tmp
# # RUN curl -LO https://github.com/paradedb/paradedb/releases/download/v0.13.2/pg_search_17-0.13.2-1PARADEDB.el8.aarch64.rpm && \
# #     rpm -ivh --nodeps pg_search_17-0.13.2-1PARADEDB.el8.aarch64.rpm

# (REMOVIDO) shared_preload_libraries de pg_search
# # RUN echo "shared_preload_libraries = 'pg_search'" >> /usr/share/postgresql/postgresql.conf.sample
