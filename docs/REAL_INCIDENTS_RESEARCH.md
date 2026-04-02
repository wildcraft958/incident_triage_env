# Real-World Incidents Research Database

This document maps real production outages to our scenario designs.
Each incident provides: what happened, root cause chain, how SREs triaged it,
and how we model it in our environment.

---

## INCIDENT DATABASE

### INC-001: Meta/Facebook Global Outage (Oct 4, 2021)

**Source**: https://engineering.fb.com/2021/10/05/networking-traffic/outage-details/

**What Happened**:
During routine maintenance, a command was issued to assess backbone capacity.
The command unintentionally took down all backbone connections, disconnecting
all Meta data centers globally. BGP routes were withdrawn, DNS servers became
unreachable, and all Meta services went offline for 6+ hours.

**Root Cause Chain**:
```
backbone-router config change
  -> BGP route withdrawal
    -> DNS unreachable
      -> all services return SERVFAIL
        -> CDN edge nodes can't resolve origins
          -> everything offline
```

**Key SRE Observations During Triage**:
- All error dashboards showed "no data" (monitoring was also down)
- External monitoring (e.g., Downdetector) was the first signal
- Internal debugging tools were also affected (circular dependency)
- Physical access to data centers was needed because remote tools were down

**What Makes This Hard to Triage**:
- The monitoring system itself is broken, so you can't see the problem
- The symptom (everything down) is too broad to point to root cause
- The root cause is at the network layer, not the application layer

**Our Scenario Mapping** -> `hard-meta-bgp-001`
- Adapted: We simulate monitoring blindness -- some metrics show "N/A" or stale data
- Root cause: network-controller `config_error` -> `rollback`
- Causal chain: network-controller -> dns-resolver -> api-gateway -> all services
- Challenge: Agent must recognize stale/missing monitoring data as itself a symptom

---

### INC-002: AWS us-east-1 Outage (Dec 7, 2021)

**Source**: https://aws.amazon.com/message/12721/

**What Happened**:
An automated activity to scale capacity on the internal network triggered
unexpected behavior, causing congestion on devices connecting the internal
network to the main AWS network. This caused Kinesis to fail, which broke
CloudWatch, which broke monitoring for everything else.

**Root Cause Chain**:
```
network-scaling-automation overload
  -> internal network congestion
    -> Kinesis data streams failed
      -> CloudWatch metrics ingestion stopped
        -> Lambda cold start monitoring broken
          -> Autoscaling couldn't read metrics
            -> cascading capacity issues
```

**Key SRE Observations**:
- CloudWatch itself went down, so alarms stopped firing
- Teams initially thought individual services were failing independently
- It took hours to realize it was all rooted in internal network congestion
- The "fix" was to reduce network traffic, which paradoxically required
  tools that used the congested network

**Our Scenario Mapping** -> `hard-aws-cascade-001`
- Adapted: Event streaming service overloaded -> monitoring pipeline breaks ->
  downstream services appear to fail independently
- Root cause: event-stream-service `cpu_saturated` -> `scale_up`
- Challenge: Agent sees multiple independent-looking failures but must find single root

---

### INC-003: CrowdStrike Channel File 291 (Jul 19, 2024)

**Source**: https://www.crowdstrike.com/blog/falcon-content-update-preliminary-post-incident-report/

**What Happened**:
A content configuration update (Channel File 291) contained a logic error.
When the CrowdStrike Falcon sensor processed the update, it triggered an
out-of-bounds memory read -> null pointer -> BSOD on 8.5 million Windows machines.

**Root Cause Chain**:
```
config-distribution-service pushes bad channel file
  -> endpoint-agents process file
    -> memory access violation in sensor
      -> kernel panic / BSOD
        -> machines unreachable
          -> services running on those machines go down
```

**Key SRE Observations**:
- Not a code deployment -- it was a configuration/content update
- The update pipeline had validation, but the validator itself had a gap
- All machines crashed nearly simultaneously (within minutes of update push)
- Recovery required physical access or safe-mode boot on millions of machines

**Our Scenario Mapping** -> `medium-crowdstrike-config-001`
- Adapted: config-service pushes bad config -> multiple worker services crash simultaneously
- Root cause: config-service `config_error` -> `rollback`
- Pattern: All downstream services crash around the same timestamp (temporal correlation)
- Red herring: Each crashed service shows its OWN error (OOM, segfault) but the real cause is the config push

---

### INC-004: GitHub Actions DB Connection Exhaustion (Multiple 2023-2024)

**Source**: https://www.githubstatus.com/history + GitHub engineering blog

**What Happened**:
A service in GitHub's microservice architecture had a connection leak -- it
would acquire PostgreSQL connections but not release them under certain error
paths. Over hours, the connection pool filled up. When it hit max_connections,
new queries were blocked, causing timeouts that cascaded through dependent services.

**Root Cause Chain**:
```
service-A connection leak (slow, over hours)
  -> postgres-db max_connections reached
    -> service-A queries block/timeout
      -> service-B (depends on A) starts timing out
        -> api-gateway returns 503
```

**Key SRE Observations**:
- Gradual degradation, not sudden crash
- The leaking service's logs showed no errors (connections were "acquired successfully")
- Postgres logs showed connection count climbing, then "FATAL: too many connections"
- Red herring: Other services using same DB worked fine (different pool/role)
- Connection leak only triggered on a specific error path that happened intermittently

**Our Scenario Mapping** -> `medium-github-connleak-001`
- Adapted: inventory-service leaks postgres connections -> order-service times out
- Root cause: postgres-db `connection_leak` -> `increase_pool` (or restart leaking service)
- Key evidence: postgres logs show connection count climb + idle connections from one client
- Red herring: payment-service also uses postgres but works fine

---

### INC-005: Google Cloud Network Outage (Jun 2, 2019)

**Source**: https://status.cloud.google.com/incident/cloud-networking/19009

**What Happened**:
A network configuration change intended for a small number of servers in one
region was accidentally applied to a much larger number across multiple regions.
This caused severe network congestion. The congestion triggered autoscalers to
create more instances, which created MORE network traffic, worsening the congestion.

**Root Cause Chain**:
```
network-config-service applies change too broadly
  -> network congestion across regions
    -> packet loss on inter-service communication
      -> services experience elevated latency
        -> autoscaler sees "service unhealthy" -> scales UP
          -> more instances -> MORE network traffic
            -> congestion worsens (feedback loop)
```

**Our Scenario Mapping** -> `hard-google-feedback-001`
- Adapted: Load balancer misconfiguration -> traffic storm -> autoscaler feedback loop
- Root cause: load-balancer `config_error` -> `fix_config`
- Challenge: Agent sees autoscaler scaling up (looks like correct behavior) but scaling IS the problem

---

### INC-006: Cloudflare BGP Route Leak (Jun 21, 2022)

**Source**: https://blog.cloudflare.com/cloudflare-outage-on-june-21-2022/

**What Happened**:
A change to Cloudflare's network intended to increase resilience accidentally
removed BGP route advertisements for 19 data centers. Traffic couldn't reach
those locations, causing significant portions of traffic to fail.

**Our Scenario Mapping** -> `medium-cloudflare-routes-001`
- Adapted: Service mesh routing configuration update drops routes to backend services
- Root cause: service-mesh-proxy `config_error` -> `rollback`

---

### INC-007: Slack Provisioning Storm (May 12, 2020)

**Source**: https://slack.engineering/a-terrible-horrible-no-good-very-bad-day-at-slack/

**What Happened**:
A surge in traffic caused Slack's provisioning system to spin up new instances.
The new instances all hit the configuration service simultaneously for bootstrap,
overwhelming it. This created a thundering herd that made the config service
unresponsive, which prevented new instances from starting, which meant traffic
couldn't be served.

**Our Scenario Mapping** -> `medium-slack-thunderherd-001`
- Adapted: autoscaler provisions new instances -> all hit config-service simultaneously
- Root cause: config-service `cpu_saturated` -> `scale_up` (the config service, not the app)

---

### INC-008: Real ML Pipeline Staleness (Industry-wide pattern)

**Sources**:
- https://mlops.community/ (multiple case studies)
- "Hidden Technical Debt in ML Systems" (Google, 2015)
- Uber's Michelangelo outage reports

**What Happened** (composite of real incidents):
A Kafka broker ran out of disk space, stopping message consumption. A feature
engineering pipeline that consumed from Kafka stopped receiving data. The feature
store continued serving features but they became progressively stale. The ML model
server used stale features and produced increasingly poor predictions. The
recommendation service showed declining engagement, but returned 200 OK on every request.

**Root Cause Chain**:
```
kafka-broker disk full
  -> kafka-consumer stops consuming
    -> feature-store features become stale (hours old)
      -> ml-model-server predictions degrade (using outdated features)
        -> recommendation-service quality drops
          -> A/B test metrics show 30% CTR decline
            -> NO services report errors
```

**Key SRE Observations**:
- ZERO error rate across all services -- everything returns 200
- The only signal is a business metric (CTR drop) in an A/B test dashboard
- The feature-store logs show "serving stale features" WARN but no ERROR
- Kafka-broker logs show FATAL: disk full -- but it's 3 services away from symptom
- Time lag: broker failed 2 hours ago, symptoms appeared gradually

**Our Scenario Mapping** -> `hard-kafka-staleness-001`
- This is our BEST hard scenario -- genuinely challenges frontier models
- Root cause: kafka-broker `disk_full` -> `clear_disk`
- Causal chain: 5 services deep
- No error signals at application layer

---

## LOG PATTERNS FROM LOGHUB

### Source: github.com/logpai/loghub (Zhu et al., ICSE 2023)

These are REAL log templates extracted from production systems.
We adapt them for our scenarios to make logs feel authentic.

#### HDFS Log Templates (adapted for our distributed storage scenarios):
```
{timestamp} INFO dfs.DataNode$DataXceiver: Receiving block blk_{id} src: /{ip}:{port} dest: /{ip}:{port}
{timestamp} INFO dfs.FSNamesystem: BLOCK* NameSystem.addStoredBlock: blockMap updated: {ip} is added to blk_{id} size {size}
{timestamp} WARN dfs.DataNode$DataXceiver: IOException: Connection reset by peer
{timestamp} ERROR dfs.DataNode$DataXceiver: Got exception for blk_{id}: java.io.IOException: Premature EOF from inputStream
```

#### OpenStack Log Templates (adapted for our service orchestration scenarios):
```
{timestamp} INFO nova.osapi_compute.wsgi.server: {ip} "GET /v2/{project}/servers/detail HTTP/1.1" status: {code} len: {len} time: {time}
{timestamp} WARNING nova.compute.manager: Instance {uuid} not found in DB, but exists on hypervisor
{timestamp} ERROR oslo_messaging._drivers.amqpdriver: MessageDeliveryFailure: Unable to connect to AMQP server after {n} tries
{timestamp} CRITICAL nova.compute.manager: Error during reboot of instance {uuid}: VirtualInterfaceCreateException
```

#### Spark Log Templates (adapted for our data processing scenarios):
```
{timestamp} INFO scheduler.TaskSetManager: Finished task {id} in stage {id} (TID {id}) in {ms} ms on {host} (executor {id})
{timestamp} WARN storage.BlockManager: Block rdd_{id} already exists on this machine; not re-adding it
{timestamp} ERROR executor.CoarseGrainedExecutorBackend: RECEIVED SIGNAL TERM
{timestamp} FATAL scheduler.LiveListenerBus: SparkListenerBus has already stopped! Dropping event {event}
```

### How We Use These:
- Extract the PATTERN (timestamp + level + component + message structure)
- Replace component names with our service names
- Keep the FEEL of real logs -- exception names, metric values, connection states
- Add realistic details: IP addresses, port numbers, query times, thread IDs

---

## FAULT TYPE TAXONOMY (Based on Real Incidents)

| Fault Type | Real Examples | Frequency in Production | Detection Difficulty |
|-----------|--------------|------------------------|---------------------|
| `oom` | Java heap exhaustion, container OOMKilled | Very High | Easy -- clear error messages |
| `disk_full` | WAL logs filling disk, Kafka log segments | High | Easy-Medium -- depends on monitoring |
| `connection_leak` | DB pool exhaustion, socket leaks | Medium | Medium -- gradual, logs show no errors |
| `cpu_saturated` | Query of death, regex backtrack, crypto ops | Medium | Easy -- CPU metrics spike |
| `config_error` | Bad deploy config, feature flag, routing rule | High | Hard -- error appears in downstream services |
| `network_partition` | BGP withdrawal, NIC failure, DNS failure | Low | Very Hard -- monitoring may also be affected |
| `dependency_timeout` | External API slow, third-party outage | High | Medium -- timeout errors in logs |
| `certificate_expired` | TLS/mTLS cert expiry | Medium | Medium -- intermittent connection failures |
| `memory_leak` | Gradual memory growth over days | Medium | Hard -- slow degradation |
| `thread_deadlock` | Lock contention, distributed deadlock | Low | Hard -- service appears hung, no errors |
| `dns_failure` | DNS cache poisoning, resolver failure | Low | Medium-Hard -- intermittent failures |

---

## REMEDIATION MAPPING

| Fault Type | Primary Remediation | Why |
|-----------|-------------------|-----|
| `oom` | `restart` | Clear memory, investigate leak later |
| `disk_full` | `clear_disk` | Remove old logs/data, resize later |
| `connection_leak` | `increase_pool` + restart leaker | Immediate relief + fix source |
| `cpu_saturated` | `scale_up` | Add capacity |
| `config_error` | `rollback` | Revert to last known good config |
| `network_partition` | `update_routes` or `failover` | Restore connectivity |
| `dependency_timeout` | `failover` | Switch to backup/circuit break |
| `certificate_expired` | `renew_certificate` | Issue new cert |
| `memory_leak` | `restart` | Immediate fix, investigate later |
| `thread_deadlock` | `kill_threads` or `restart` | Break the deadlock |
| `dns_failure` | `flush_dns` | Clear poisoned cache |
