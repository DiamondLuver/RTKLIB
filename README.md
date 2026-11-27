# RTKLIB 2.4.3 b34 — rtkrcv for macOS

This is [RTKLIB](https://github.com/tomojitakasu/RTKLIB) 2.4.3 b34 with fixes
that make the real-time positioning program `rtkrcv` build and run on macOS,
plus a sample configuration and a small web UI for it.

- **Setup, running, the web UI and what to put for each configuration option:**
  [app/consapp/rtkrcv/README.md](app/consapp/rtkrcv/README.md)
- **Original RTKLIB readme and update history:** [readme.txt](readme.txt)

Quick start:

```bash
cd app/consapp/rtkrcv/gcc && make
cp ../../../../.env.example ../../../../.env   # .env in the repository root: put your caster login in it
./rtkrcv -s -o ../conf/single.conf
```
