# CLAUDE.md

## Project Overview

This project implements a **distributed, tag-based filesystem** designed to be robust, safe, and simple to operate in a multi-host environment. The system prioritizes **Availability and Partition Tolerance (AP)** and uses an **eventual consistency** model with a bounded convergence target: **tens of seconds** after normal connectivity is restored.

All existing features, commands, and behaviors in the current codebase **MUST be preserved**. No technology stack changes are permitted.

---

## Non-Negotiable Deployment Model

### Containerization Rules

* **All components MUST run inside Docker containers**
* **Docker Swarm is strictly mandatory**
* **All containers MUST be deployed using `docker run`**
* The following are **forbidden**:

  * `docker service`
  * `docker compose`
  * `docker stack`
  * Any orchestration abstraction beyond raw `docker run`
* All containers MUST run inside a **Docker Swarm overlay network**
* Deployment is **ALWAYS manual**

  * Scripts MAY exist
  * Scripts MUST NOT be used for deployment
  * Scripts serve documentation or legacy purposes only

---

## Mandatory Deployment Procedure

The system **MUST** operate correctly using these steps **exactly as written**.

### 1. Initialize Docker Swarm

```bash
docker swarm init
```

All additional hosts MUST join the swarm **as managers**.

### 2. Create the Overlay Network

```bash
docker network create --driver overlay --attachable dfs-network
```

### 3. Build Images

```bash
docker build -f docker/Dockerfile.controller -t redcloud-controller:latest .
docker build -f docker/Dockerfile.chunkserver -t redcloud-chunkserver:latest .
docker build -f docker/Dockerfile.cli -t redcloud-cli:latest .
```

### 4. Run Controller Containers

Controllers may be started in any order.

```bash
docker run -d --network dfs-network --network-alias controller redcloud-controller:latest
docker run -d --name controller-1 --network dfs-network --network-alias controller redcloud-controller:latest
...
docker run -d --name controller-# --network dfs-network --network-alias controller redcloud-controller:latest
```

Rules:

* The **network alias `controller` is mandatory**
* Container names are only for logs and debugging
* The system MUST assume **multiple controllers exist**
* Startup order MUST NOT affect correctness

### 5. Run Chunk Servers (Alias Mandatory)

Chunk servers may be started in any order.

```bash
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
docker run -d --name chunkserver-1 --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
...
docker run -d --name chunkserver-# --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
```

Rules:

* The **network alias `chunkserver` is mandatory**
* Container names are only for logs and debugging
* The system MUST assume **multiple chunk servers exist**
* Startup order MUST NOT affect correctness

### 6. Run CLI Client

```bash
docker run -it --rm \
    --network dfs-network \
    -v "$(pwd):/uploads" \
    -v "$(pwd)/downloads:/downloads" \
    -w /uploads \
    redcloud-cli:latest
```

---

## Service Discovery

### Docker DNS Only (No Fallback)

* **All service discovery MUST occur via Docker Swarm DNS**
* Discovery MUST be done via DNS resolution (e.g., `nslookup`)
* Discovery anchors are:

  * `controller`
  * `chunkserver`

Explicitly forbidden:

* Static IPs or hostnames
* Configuration files listing endpoints
* Environment-variable discovery overrides
* External registries
* Gossip-only discovery without DNS
* Any fallback mechanism of any kind

If Docker DNS fails, the system is allowed to fail.

---

## Persistence and Storage Constraints

* **Using shared volumes is strictly forbidden**
* No shared Docker volumes across containers
* No external storage assumptions
* **No persistence between sessions is acceptable**
* Containers do **not** need to survive restarts without data loss

Consequences:

* Replication guarantees apply **only within a running session**
* Robustness is defined as surviving node loss during runtime, not preserving state across full teardown/restart

---

## Consistency and Replication Requirements

### Critical Convergence Requirements

The system MUST guarantee eventual convergence (within tens of seconds after healing):

* **All controllers MUST eventually contain the same metadata**
* **All controllers MUST eventually contain the same user/auth data**
* **All controllers MUST eventually converge on user session/sign-in state**
* **All chunk servers MUST eventually contain the same file data**

Permanent divergence is a critical failure.

### User Session and Sign-In Convergence (Clarification)

When a user signs in to **any** controller:

* That controller MUST record the sign-in/session event as replicated state
* **Other controllers MUST eventually observe that the user is signed in**
* Convergence MUST occur within the same bounded “tens of seconds” expectation

During partitions, different controllers may temporarily disagree about a user’s signed-in status. After healing, controllers MUST reconcile and converge deterministically.

### AP and Partition Rules

* The system MUST remain available during partitions
* Nodes MUST continue serving requests with local knowledge
* Divergence is permitted during partitions
* When partitions heal, replication MUST reconcile all state to convergence without manual intervention

---

## Controller Subsystem Requirements

### Controller Storage (SQLite)

Controllers store metadata and user/auth data in a **SQLite database**. SQLite is treated as a **local materialized store** and **not** as a replicated file artifact.

User session/sign-in state is part of the controller-owned replicated state and MUST be represented in SQLite in a replicable way.

### Safer Minimal Replication Model for Controllers (Recommended)

Controllers MUST replicate by exchanging **logical operations** and applying them idempotently, rather than replicating SQLite database files.

Required properties:

* Operations are durable within the session and replayable
* Application is idempotent
* Operations are causally ordered when possible
* Concurrent operations are resolved deterministically

### Anti-Entropy + Gossip Replication (Mandatory)

Controllers MUST use:

* **Gossip** to exchange membership/liveness hints and replication summaries
* **Anti-entropy** to reconcile missing state until convergence
* **Vector clocks** (or an equivalent causality-tracking scheme) to detect concurrent updates

Replication MUST rely on Docker DNS to discover peers:

* Controllers obtain the peer set exclusively via `nslookup controller`

### Conflict Resolution Policy (Safer Minimal Approach)

The system MUST use deterministic conflict handling:

* For scalar fields (values that should have a single winner), **Last-Write-Wins (LWW)** is acceptable.
* For tag associations and other set-like metadata, the recommended safe approach is **set-convergent semantics** that do not lose concurrent updates.
* For sign-in/session state, the system MUST use deterministic resolution that converges; it MUST be represented as replicated state and not as purely local memory.

### User/Auth Data Replication (Mandatory)

All user and authorization information MUST be replicated across controllers under the same replication mechanism, including:

* User accounts and metadata
* API keys
* Access control information
* Sign-in/session events and sign-in/session status

No controller may be a single point of truth. Any controller may serve any request.

---

## Chunk Server Subsystem Requirements

### Full Replication Mandate

All chunk servers MUST eventually contain the same file data.

This means:

* Any chunk written to the system must be replicated to **every chunk server** within tens of seconds (normal conditions).
* If a chunk server is temporarily unreachable, it MUST be brought up-to-date after it becomes reachable.

### Safer Minimal Data Model for Chunk Servers (Recommended)

Chunk data SHOULD be treated as:

* **Immutable once written**
* Identified by a stable identifier derived from content or a deterministic scheme

This reduces conflict complexity and makes anti-entropy repair safe.

### Chunkserver Anti-Entropy (Mandatory)

Chunk servers MUST run an anti-entropy protocol to reconcile missing data with peers.

Required properties:

* It must converge efficiently as data scales
* It must support “compare summaries, exchange differences”
* It must not require a central coordinator
* It must operate under partitions and heal afterward

Chunkserver peer discovery MUST be via:

* `nslookup chunkserver`

### Deletion and Garbage Collection

Deletes MUST converge and MUST NOT resurrect after partitions heal.

Required properties:

* Deletions must be represented in a way that can replicate (tombstones or equivalent)
* Garbage collection must be conservative enough to prevent deleted data from reappearing due to delayed replication
* Delete semantics must remain consistent with the existing CLI behavior

---

## Controller ↔ Chunkserver Coordination

* Controllers and chunk servers MUST use DNS-only discovery:

  * Controllers discover chunk servers via `chunkserver`
  * Chunk servers discover controllers via `controller`
* Controllers manage metadata that maps logical files/tags to stored chunks
* Chunk servers store chunk data and participate in full replication
* The design must tolerate:

  * Controllers missing temporarily
  * Chunk servers missing temporarily
  * Network partitions and re-merges

---

## Operational Convergence Target

Replication parameters MUST be tuned so that under normal conditions (same LAN, Ethernet/WiFi/hotspot), convergence occurs within **tens of seconds**.

This is a functional requirement for testing.

---

## Multi-Host Environment Requirements

The system will be tested on:

* Multiple Ubuntu 24.04 hosts (laptops)
* Ethernet or local WiFi, including hotspot-style networks
* Any number of hosts (not fixed)

Any container can run on any host. The system MUST NOT depend on:

* Fixed IPs
* Hostnames outside Docker DNS
* Static topology assumptions

---

## Logging and Observability Requirements (Mandatory)

### Operational Constraint

Debugging will be performed using Docker logs:

```bash
docker logs -f <controller-container-id>
docker logs -f <chunkserver-container-id>
```

Therefore:

* All components MUST log relevant events to **stdout/stderr**
* No dependency is allowed on:

  * shared volumes
  * external log collectors
  * sidecars
  * host agents

### What Must Be Logged

Controllers and chunk servers MUST log, at minimum:

* Startup/shutdown lifecycle events
* DNS discovery results and peer set changes
* Connection attempts and failures (with reasons)
* Request handling outcomes (success/failure) with identifiers suitable for correlation
* Replication activity:

  * anti-entropy cycles
  * missing state detected
  * state applied
  * conflict resolution decisions
* Partition symptoms and recovery progress
* Security-relevant events (sanitized):

  * authentication attempts
  * authorization denials
  * API key lifecycle events
  * sign-in and sign-out events (sanitized)

### Log Safety Requirements

* Logs MUST NOT include secrets (API keys, passwords, tokens)
* Logs MUST be consistent enough to support multi-container debugging and timeline reconstruction

---

## Code Style Rules

### Comments

* **Inline comments are forbidden**
* Allowed:

  * Docstrings
  * `TODO` comments only

---

## Behavioral Stability

* Preserve all existing commands, APIs, and behaviors
* Backward compatibility is mandatory
* Refactoring MUST NOT change observable behavior unless explicitly documented in project docs

---

## AI Contribution Rules

When modifying or generating code:

* Never introduce forbidden deployment mechanisms
* Never change discovery behavior (DNS-only)
* Never change the mandatory deployment commands
* Never add inline comments
* Always preserve AP behavior during partitions
* Always guarantee eventual convergence requirements:

  * controllers converge on metadata, user/auth data, and sign-in/session state
  * chunk servers converge on file data
* Always emit useful stdout/stderr logs for debugging

If any request conflicts with this document, **this document takes precedence**.

---

## Summary

This project is a distributed tag-based filesystem deployed manually on Docker Swarm using raw `docker run`, overlay networking, and Docker DNS-only discovery. It is AP-first, heals after partitions, and converges within tens of seconds under normal test conditions.

**All controllers MUST eventually contain the same metadata, user/auth data, and user sign-in/session state.**
**All chunk servers MUST eventually contain the same file data.**
No shared volumes are allowed, and persistence across restarts is not required.
