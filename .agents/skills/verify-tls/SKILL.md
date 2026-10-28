---
name: verify-tls
description: Verify spicepy's TLS handling (tls_root_cert, mTLS, TLS error messages) against a live Spice runtime serving a certificate from a private CA. Use after changing spicepy/_http.py, the ADBC connection setup in spicepy/_client.py, or anything that touches certificates.
---

# Verify spicepy TLS against a live runtime

A private CA is in neither the system nor the certifi bundle, so a call only
passes if it verifies against `tls_root_cert`. Unit tests mock the transports;
this is the check that the real Flight, ADBC, and HTTP stacks agree.

## 1. Certificates (throwaway, never commit)

```bash
mkdir -p /tmp/spicepy-tls/certs && cd /tmp/spicepy-tls/certs
openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.pem -days 1 \
  -subj "/CN=spicepy test CA" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=localhost"
printf "subjectAltName=DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n" > ext.cnf
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out server.pem -days 1 -extfile ext.cnf
openssl req -x509 -newkey rsa:2048 -nodes -keyout wrongca.key -out wrongca.pem -days 1 -subj "/CN=wrong CA"
```

## 2. Runtime

Use the `spicepod.yaml` from the "Start TLS spice runtime with a private CA"
step in `.github/workflows/test.yml` (API key `spicepy-tls-key:rw`, TLS on,
one `memory:store` dataset), then:

```bash
cd /tmp/spicepy-tls
spiced --http 127.0.0.1:18443 --flight 127.0.0.1:50071 --metrics 127.0.0.1:19091 \
  --node-bind-address 127.0.0.1:50072 &> spice.log &
curl -sf --cacert certs/ca.pem https://127.0.0.1:18443/v1/ready
```

## 3. Run

```bash
export SPICE_TLS_FLIGHT_URL=grpc+tls://127.0.0.1:50071
export SPICE_TLS_HTTP_URL=https://127.0.0.1:18443
export SPICE_TLS_API_KEY=spicepy-tls-key
export SPICE_TLS_ROOT_CERT=/tmp/spicepy-tls/certs/ca.pem
export SPICE_TLS_WRONG_CA=/tmp/spicepy-tls/certs/wrongca.pem
pytest -q tests/test_integration_tls.py
```

Pass means: every transport works with only `tls_root_cert` set (the test strips
`REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE`), and a wrong CA raises `SpiceTLSError` in
under 2 seconds. A run taking about a minute per HTTP test means SSL errors are
being retried again.

## 4. Clean up

`kill %1` (or the spiced pid) and `rm -rf /tmp/spicepy-tls`.
