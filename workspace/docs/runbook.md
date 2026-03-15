# Operations Runbook

## Deployment

1. Run tests: `pytest tests/`
2. Build image: `docker build -t my-service .`
3. Deploy to staging: `kubectl apply -f deploy/staging.yaml`
4. Verify health: `curl https://staging.example.com/health`
5. Deploy to production: `kubectl apply -f deploy/production.yaml`

## Incident Response

### High CPU Usage
- Check for runaway queries: `SELECT * FROM pg_stat_activity WHERE state = 'active';`
- Scale horizontally: `kubectl scale deployment my-service --replicas=4`

### Database Connection Errors
- Verify connectivity: `pg_isready -h db.internal.example.com`
- Check pool exhaustion in metrics dashboard
- Restart if needed: `kubectl rollout restart deployment my-service`
