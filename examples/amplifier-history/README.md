# amplifier-foundation decision journal

`journal.json` is a dated list of 58 facts and decisions taken from the real git history of microsoft/amplifier-foundation. That history has 602 commits, from 2025-12-09 (c1d26bf, "initial import") to 2026-07-07 (a425df9, the latest commit).
Entries were picked by reading the full commit log and keeping the changes that shape how the project evolved: defaults turned on or off, components added, replaced or renamed, policy changes, and reverts.
Each entry was checked against its commit message, and against the body and diff stat where needed. A script then confirmed that every cited hash, date and subject line matches the repository exactly.
Every entry cites its commit in the `evidence` field as "commit HASH: original subject line". Nothing is invented.
When a later commit replaces an earlier decision, the later entry has a `supersedes` field pointing at the earlier entry's `id`. This lets the graph show what was believed at each point in time and what replaced it. There are 20 such supersessions; one example is token streaming going enabled, then disabled, then enabled again.
Entries that only add to the record, such as new behaviors included by default, carry no id.

Licence: microsoft/amplifier-foundation is MIT licensed, Copyright (c) Microsoft Corporation
(https://github.com/microsoft/amplifier-foundation/blob/main/LICENSE). See NOTICE at the repository root.
