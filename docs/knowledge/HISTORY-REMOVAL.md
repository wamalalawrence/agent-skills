# Removing merged data from a knowledge source

A knowledge source is a git repository, and git keeps history. **Deleting or reverting a file
does not remove it.** Every clone, fork, open pull request, CI cache, and host backup still holds
it. Treat anything that merged as disclosed to everyone who could read the source.

`knowledge check` runs in CI to block the common cases before merge: credential-shaped values,
transcript text, code snippets, email addresses, and person names outside the source's policy.
That lowers the odds of needing this runbook; it does not remove the need for it.

## A credential merged

Order matters: the credential is the emergency, not the file.

1. **Rotate the credential first.** Revoke it at its issuer and issue a new one. Assume it has
   already been copied. Nothing below makes the old value safe again.
2. **Revert** the fact in a normal pull request, so the current tree is clean for everyone who
   syncs.
3. **Rewrite history** to remove the value from every commit. This needs a source admin and a
   maintenance window:

   ```bash
   git clone --mirror git@example.com:acme/engineering-knowledge.git
   cd engineering-knowledge.git
   git filter-repo --replace-text ../expressions.txt   # a line such as: <the value>==>[removed]
   git push --force --mirror                           # needs branch protection lifted temporarily
   ```

   Restore branch protection immediately afterwards.
4. **Ask the host to purge caches.** Most hosts keep unreachable objects, pull-request refs, and
   forks. Follow your host's "remove sensitive data" procedure and support process. Forks made
   by other people are outside your control.
5. **Tell every engineer to sync.** A client that sees rewritten history re-points its clone,
   then expires the reflog and prunes unreachable objects, so the old objects leave its cache.
   Nothing else on their machines holds the value: the local index is rebuilt from the clone.
6. **Record the incident** the way your organisation records credential exposure.

## Personal data merged

Same steps, minus rotation. Revert, rewrite history, ask the host to purge, and have engineers
sync. If the data is covered by an erasure obligation, involve whoever owns that obligation
before you start, because the host's retention of unreachable objects and backups may matter.

## Wrong but harmless facts

Do not rewrite history for a fact that is simply wrong. Propose a supersession
(`knowledge propose <new> --supersedes <old>`) or mark it STALE. History is the audit trail, and
superseded facts stay queryable as history.
