FROM postgres:17.5

# Instala dependências
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    postgresql-server-dev-all \
    python3.11 \
    python3-pip \
    postgresql-plpython3-16 \
    && rm -rf /var/lib/apt/lists/*

# Clona repositórios
WORKDIR /tmp
RUN git clone https://github.com/pgvector/pgvector.git

# Compila pgvector
WORKDIR /tmp/pgvector
RUN make
RUN make install
