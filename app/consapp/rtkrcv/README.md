# rtkrcv on macOS

`rtkrcv` is RTKLIB's command-line real-time positioning program. It reads GNSS
data from a receiver or an NTRIP caster, computes positions, and writes them to
a file or a network port.

This folder is RTKLIB 2.4.3 b34 with the fixes needed to build and run `rtkrcv`
on macOS, a sample configuration, and a small web UI for editing the
configuration and watching the solution.

- [Setup](#setup)
- [Running](#running)
- [Web UI](#web-ui)
- [Configuration](#configuration)
- [Option reference](#option-reference)
- [Troubleshooting](#troubleshooting)
- [Changes from RTKLIB 2.4.3 b34](#changes-from-rtklib-243-b34)

## Setup

You need the Xcode command line tools (`xcode-select --install`) for `make` and
the C compiler. The web UI additionally needs Python 3.7 or later; it uses no
extra packages.

1. Build `rtkrcv`:

   ```bash
   cd app/consapp/rtkrcv/gcc
   make
   ```

   This produces `app/consapp/rtkrcv/gcc/rtkrcv`.

2. Put your caster login in `.env` in the repository root:

   ```bash
   cd ../../../..
   cp .env.example .env
   ```

   Then edit `.env`:

   ```
   NTRIP_USER=your-caster-user
   NTRIP_PASSWORD=your-caster-password
   NTRIP_HOST=caster.example.com
   NTRIP_PORT=2101
   NTRIP_MOUNTPOINT=MOUNTPOINT
   ```

   Git ignores `.env`, so the login is never committed. The sample
   configuration `single.conf` refers to these values by name and contains no
   login itself; see [Logins and private values](#logins-and-private-values).

3. Adjust anything else in `conf/single.conf`. See
   [Configuration](#configuration).

## Running

Start it from the `gcc` folder, because relative paths in the configuration
(such as `./output/...`) are resolved from the folder you start it in:

```bash
cd app/consapp/rtkrcv/gcc
./rtkrcv -s -o ../conf/single.conf
```

`-s` starts processing immediately and `-o` names the configuration file. You
get a `rtkrcv>` prompt; nothing else is printed until you type a command:

| Command | Shows |
|---|---|
| `status` | Solution state, position, satellite counts |
| `stream` | Each input and output, whether it is connected, bytes in and out |
| `satellite` | The satellites in use |
| `solution 1` | A new position line every second (Ctrl-C to stop) |
| `shutdown` | Stops the server and exits |
| `help` | All commands |

Always leave with `shutdown`. Closing the terminal window instead leaves
`rtkrcv` running in the background, still holding the caster login and the
output port; the next copy you start then gets no data. `pgrep -l rtkrcv` lists
running copies and `pkill rtkrcv` stops them.

With the sample configuration the solution goes to two places:

- TCP port 10009: run `nc localhost 10009` in a second terminal to watch it.
- The file `gcc/output/trcrv_single.pos`, overwritten on each start.

The message `no navigation data: rtkrcv.nav` at startup is harmless. That file
is a cache of satellite orbit data, written on shutdown and read on the next
start.

## Web UI

```bash
cd app/consapp/rtkrcv/ui
python3 server.py
```

This opens `http://127.0.0.1:8765/`. It edits `conf/single.conf`; use
`--conf FILE` for another file and `--port N` for another port.

- **Configuration pages** show every option in the file with the values this
  build accepts. Saving rewrites only the lines you changed; comments and
  layout are kept. Edits made to the file in a text editor appear in the page
  within a couple of seconds.
- **Start / Stop / Restart** run `rtkrcv` with that file. Changes take effect on
  restart, and the page says when the running copy is behind the file.
- **Monitor** shows the solution, the streams and the satellites, updated every
  second.

The page is served on this computer only. Ctrl-C in the terminal stops the UI
and the `rtkrcv` it started. Stop any `rtkrcv` running in a terminal before
pressing Start, or the two compete for the same caster login and ports; the
page warns when it sees one.

## Configuration

The configuration is a text file of `name =value` lines. Everything after `#`
is a comment. Options left out keep their defaults, and a misspelt option name
is ignored without any message.

The explanatory comments in `single.conf` (the lists in brackets) were written
for an older RTKLIB and some are out of date. Use the tables below, or the web
UI, for the values this build accepts.

### Logins and private values

Keep logins out of the options file. In any stream path (`inpstrN-path`,
`outstrN-path`, `logstrN-path`), `${NAME}` is replaced when the server starts:

```
inpstr1-path       =${NTRIP_USER}:${NTRIP_PASSWORD}@${NTRIP_HOST}:${NTRIP_PORT}/${NTRIP_MOUNTPOINT}
```

`rtkrcv` takes each value from the environment variable `NAME` or, if that is
not set, from a file named `.env`. It looks for `.env` in the folder of the
options file, then in each folder above it up to the top of the repository,
and uses the first one it finds. The normal place is the repository root; a
`.env` beside one options file overrides it for that file. An environment
variable overrides both:

```bash
NTRIP_MOUNTPOINT=OTHER ./rtkrcv -s -o ../conf/single.conf
```

`.env` holds one `NAME=VALUE` per line. The value is the rest of the line, so a
password may contain `#`, `@`, `:` or spaces; quotes around it are optional.
Lines starting with `#` are comments. The names are free: use any you like in
the path and define the same ones in `.env`.

If a name is not set anywhere, the server refuses to start and says which one.
The `option` and `save` console commands and the web UI show the path as
written, with the placeholders. The filled-in path does appear in the first 24
characters of the `stream` command's Path column and in trace files (`-t`).

### The minimum to change

| To do this | Set |
|---|---|
| Read from an NTRIP caster | `inpstr1-type =ntripcli`, `inpstr1-format =rtcm3`, keep the sample `inpstr1-path` and put the login in `.env` |
| Read from a u-blox receiver on USB | `inpstr1-type =serial`, `inpstr1-path =cu.usbmodem1101:115200:8:n:1:off` (the device name under `/dev`), `inpstr1-format =ubx` |
| Standalone position, no base station | `pos1-posmode =single` |
| RTK with a base station | `pos1-posmode =kinematic`, fill in `inpstr2-type`, `inpstr2-path`, `inpstr2-format`, and set `ant2-postype =rtcm` |
| Choose satellite systems | `pos1-navsys` = sum of `1` GPS, `2` SBAS, `4` GLONASS, `8` Galileo, `16` QZSS, `32` BeiDou, `64` NavIC |
| Write solutions to a file | `outstr2-type =file`, `outstr2-path =./output/name.pos` |
| Serve solutions on a TCP port | `outstr1-type =tcpsvr`, `outstr1-path =:10009/` |
| Keep one output file per run | Put time keywords in the path, e.g. `./output/single_%Y%m%d_%h%M.pos` |

### Stream paths

What to put in an `inpstrN-path`, `outstrN-path` or `logstrN-path` depends on
the matching `-type`:

| Type | Path | Example |
|---|---|---|
| `serial` | `port[:bit_rate[:byte[:parity(n\|o\|e)[:stopb[:fctr(off\|on)]]]]]` | `cu.usbmodem1101:115200:8:n:1:off` |
| `file` | `path` — for input, add `::T` to replay at recorded speed; in output paths `%Y %m %d %h %M %S` are replaced by the time and `::S=hours` starts a new file at that interval | `./output/single_%Y%m%d.pos` |
| `tcpsvr` | `:port` | `:10009/` |
| `tcpcli` | `addr:port` | `192.168.0.11:10008` |
| `ntripcli` | `user:passwd@addr:port/mntpnt` | `${NTRIP_USER}:${NTRIP_PASSWORD}@${NTRIP_HOST}:2101/MOUNTPOINT` |
| `ntripsvr` | `user:passwd@addr:port/mntpnt[:str]` | |
| `ftp` | `user:passwd@addr/path` | |
| `http` | `addr/path` | |

A value in the options file cannot contain `#`, because the rest of the line
would be read as a comment. Put such a value in `.env` and refer to it with
`${NAME}`.

## Option reference

Every option this build of `rtkrcv` reads. "Accepted values" lists the names to
write for a choice, or the kind of value and its unit.

### Input streams

`inpstr1` is the rover, `inpstr2` the base station, `inpstr3` corrections.

| Option | What to put | Accepted values |
|---|---|---|
| `inpstr1-type` | Where the **rover** data comes from. Required. | `off`, `serial`, `file`, `tcpsvr`, `tcpcli`, `ntripcli`, `ftp`, `http` |
| `inpstr1-path` | Address of the rover stream, in the form that matches its type (see [Stream paths](#stream-paths)). Use `${NAME}` for the login (see [Logins and private values](#logins-and-private-values)). | text |
| `inpstr1-format` | Format of the rover data. It must match what the source really sends: `rtcm3` for most NTRIP casters, `ubx` for a u-blox receiver's raw output. A wrong format connects but decodes nothing. | `rtcm2`, `rtcm3`, `oem4`, `oem3`, `ubx`, `ss2`, `hemis`, `skytraq`, `gw10`, `javad`, `nvs`, `binex`, `rt17`, `sbf`, `cmr`, `tersus`, `sp3` |
| `inpstr2-type` | Where the **base station** data comes from. Needed for `dgps`, `kinematic`, `static`, `movingbase` and `fixed`; leave `off` for `single` and PPP. | `off`, `serial`, `file`, `tcpsvr`, `tcpcli`, `ntripcli`, `ftp`, `http` |
| `inpstr2-path` | Address of the base station stream. | text |
| `inpstr2-format` | Format of the base station data (normally `rtcm3`). | `rtcm2`, `rtcm3`, `oem4`, `oem3`, `ubx`, `ss2`, `hemis`, `skytraq`, `gw10`, `javad`, `nvs`, `binex`, `rt17`, `sbf`, `cmr`, `tersus`, `sp3` |
| `inpstr2-nmeareq` | Whether to send the rover position to the base stream as NMEA GGA. Network/VRS casters need it. `latlon` sends the fixed position below, `single` sends the current single solution. | `off`, `latlon`, `single` |
| `inpstr2-nmealat` | Latitude sent when `inpstr2-nmeareq` is `latlon`. | number (deg) |
| `inpstr2-nmealon` | Longitude sent when `inpstr2-nmeareq` is `latlon`. | number (deg) |
| `inpstr2-nmeahgt` | Height sent when `inpstr2-nmeareq` is `latlon`. | number (m) |
| `inpstr3-type` | Where **correction** data comes from (SSR corrections or precise ephemeris). Usually `off`. | `off`, `serial`, `file`, `tcpsvr`, `tcpcli`, `ntripcli`, `ftp`, `http` |
| `inpstr3-path` | Address of the correction stream. | text |
| `inpstr3-format` | Format of the correction data (`rtcm3` for SSR, `sp3` for precise orbits). | `rtcm2`, `rtcm3`, `oem4`, `oem3`, `ubx`, `ss2`, `hemis`, `skytraq`, `gw10`, `javad`, `nvs`, `binex`, `rt17`, `sbf`, `cmr`, `tersus`, `sp3` |

### Output streams

Up to two copies of the solution.

| Option | What to put | Accepted values |
|---|---|---|
| `outstr1-type` | Where solution output 1 goes. `off` for none. | `off`, `serial`, `file`, `tcpsvr`, `tcpcli`, `ntripsvr`, `ntripcas` |
| `outstr1-path` | Address of solution output 1 (see [Stream paths](#stream-paths)). For `tcpsvr`, `:10009/` means "listen on port 10009". | text |
| `outstr1-format` | Format of solution output 1: `llh` (lat/lon/height), `xyz` (ECEF), `enu` (baseline), `nmea` (GGA/RMC sentences), `stat` (solution status). | `llh`, `xyz`, `enu`, `nmea`, `stat` |
| `outstr2-type` | Where solution output 2 goes. `off` for none. | `off`, `serial`, `file`, `tcpsvr`, `tcpcli`, `ntripsvr`, `ntripcas` |
| `outstr2-path` | Address of solution output 2. For `file`, a path relative to the folder rtkrcv is started from; the folder is created if missing and the file is overwritten on each start. | text |
| `outstr2-format` | Format of solution output 2. | `llh`, `xyz`, `enu`, `nmea`, `stat` |

### Log streams

Raw copies of the three inputs.

| Option | What to put | Accepted values |
|---|---|---|
| `logstr1-type` | Where to save a raw copy of the rover input, for replay or debugging. Usually `off` or `file`. | `off`, `serial`, `file`, `tcpsvr`, `tcpcli`, `ntripsvr`, `ntripcas` |
| `logstr1-path` | Address of the rover log. | text |
| `logstr2-type` | Where to save a raw copy of the base station input. | `off`, `serial`, `file`, `tcpsvr`, `tcpcli`, `ntripsvr`, `ntripcas` |
| `logstr2-path` | Address of the base station log. | text |
| `logstr3-type` | Where to save a raw copy of the correction input. | `off`, `serial`, `file`, `tcpsvr`, `tcpcli`, `ntripsvr`, `ntripcas` |
| `logstr3-path` | Address of the correction log. | text |

### Positioning (`pos1-`)

| Option | What to put | Accepted values |
|---|---|---|
| `pos1-posmode` | Positioning mode. `single`: rover only, metre-level. `dgps`: code differential with a base. `kinematic`: RTK with a moving rover. `static`: RTK with a stationary rover. `movingbase`: both move. `fixed`: rover position known. `ppp-*`: precise point positioning. | `single`, `dgps`, `kinematic`, `static`, `movingbase`, `fixed`, `ppp-kine`, `ppp-static`, `ppp-fixed` |
| `pos1-frequency` | How many carrier frequencies to use. `l1` for single-frequency receivers, `l1+2` for dual-frequency. | `l1`, `l1+2`, `l1+2+3`, `l1+2+3+4`, `l1+2+3+4+5` |
| `pos1-soltype` | Filter direction. Real-time processing is always `forward`; the others only matter for post-processing. | `forward`, `backward`, `combined` |
| `pos1-elmask` | Elevation mask. Satellites lower than this are ignored. 10-15 is typical. | number (deg) |
| `pos1-snrmask_r` | Apply the SNR mask below to the rover. | `off`, `on` |
| `pos1-snrmask_b` | Apply the SNR mask below to the base station. | `off`, `on` |
| `pos1-snrmask_L1` | Minimum L1 signal strength (dBHz) for nine elevation bands from 5 to 85 degrees, comma-separated. `0` disables a band. | text |
| `pos1-snrmask_L2` | Same for L2. | text |
| `pos1-snrmask_L5` | Same for L5. | text |
| `pos1-dynamics` | `on` estimates receiver velocity and acceleration; use it for a moving rover in `kinematic` mode. | `off`, `on` |
| `pos1-tidecorr` | Earth tide correction. `on`: solid earth tides. `otl`: also ocean loading and pole tide (needs `file-blqfile`). Only matters for PPP and long baselines. | `off`, `on`, `otl` |
| `pos1-ionoopt` | Ionosphere correction. `brdc`: broadcast model (normal choice). `dual-freq`: ionosphere-free combination (needs two frequencies). `est-stec`: estimate it. `ionex-tec`: from `file-ionofile`. | `off`, `brdc`, `sbas`, `dual-freq`, `est-stec`, `ionex-tec`, `qzs-brdc` |
| `pos1-tropopt` | Troposphere correction. `saas`: Saastamoinen model (normal choice). `est-ztd` / `est-ztdgrad`: estimate it (PPP, long baselines). | `off`, `saas`, `sbas`, `est-ztd`, `est-ztdgrad` |
| `pos1-sateph` | Satellite orbits and clocks. `brdc`: broadcast ephemeris (normal choice). `precise`: SP3/clock files. `brdc+ssrapc` / `brdc+ssrcom`: broadcast plus SSR corrections from the correction stream. | `brdc`, `precise`, `brdc+sbas`, `brdc+ssrapc`, `brdc+ssrcom` |
| `pos1-posopt1` | Use the satellite antenna phase-centre model (needs `file-satantfile`). | `off`, `on` |
| `pos1-posopt2` | Use the receiver antenna phase-centre model (needs `file-rcvantfile`). | `off`, `on` |
| `pos1-posopt3` | Phase wind-up correction (PPP). | `off`, `on`, `precise` |
| `pos1-posopt4` | Exclude satellites in eclipse (PPP). | `off`, `on` |
| `pos1-posopt5` | RAIM fault detection: drop one bad satellite if the solution fails its check. | `off`, `on` |
| `pos1-posopt6` | Handle the receiver clock jump at day boundaries. | `off`, `on` |
| `pos1-exclsats` | Satellites to exclude, space-separated, e.g. `G04 C02`. Prefix with `+` to force-include an unhealthy one. Empty for none. | text |
| `pos1-navsys` | Satellite systems to use, as the sum of their numbers. `1` = GPS only, `5` = GPS+GLONASS, `61` = GPS+GLONASS+Galileo+QZSS+BeiDou. | sum of `1` gps, `2` sbas, `4` glo, `8` gal, `16` qzs, `32` bds, `64` navic |

### Ambiguity resolution and filter (`pos2-`)

These only matter for RTK modes (`kinematic`, `static`, `movingbase`, `fixed`).

| Option | What to put | Accepted values |
|---|---|---|
| `pos2-armode` | Integer ambiguity resolution for RTK. `continuous`: normal choice. `instantaneous`: resolve every epoch. `fix-and-hold`: hold fixed ambiguities. `off`: float only. | `off`, `continuous`, `instantaneous`, `fix-and-hold` |
| `pos2-gloarmode` | Resolve GLONASS ambiguities. | `off`, `on` |
| `pos2-bdsarmode` | Resolve BeiDou ambiguities. | `off`, `on` |
| `pos2-arthres` | Minimum ratio test value to accept a fix. `3` is the usual value; higher is stricter. | number |
| `pos2-arthres1` | Extra AR threshold not used by this build; leave at the default. | number |
| `pos2-arthres2` | Extra AR threshold not used by this build; leave at the default. | number |
| `pos2-arthres3` | Extra AR threshold not used by this build; leave at the default. | number |
| `pos2-arthres4` | Extra AR threshold not used by this build; leave at the default. | number |
| `pos2-arlockcnt` | Epochs a satellite must be tracked continuously before its ambiguity is used for a fix. | whole number |
| `pos2-arelmask` | Minimum elevation of satellites used for ambiguity resolution. | number (deg) |
| `pos2-arminfix` | Fixed epochs required before ambiguities are held (`fix-and-hold`). | whole number |
| `pos2-armaxiter` | Maximum iterations when resolving ambiguities. | whole number |
| `pos2-elmaskhold` | Minimum elevation of satellites whose ambiguities are held (`fix-and-hold`). | number (deg) |
| `pos2-aroutcnt` | Epochs without data after which a satellite's ambiguity is reset. | whole number |
| `pos2-maxage` | Oldest base station data that may be used. Beyond this the differential solution is dropped. | number (s) |
| `pos2-syncsol` | `on` waits for base data of the same epoch before outputting a solution; `off` outputs immediately. | `off`, `on` |
| `pos2-slipthres` | Cycle slip detection threshold on the geometry-free combination. | number (m) |
| `pos2-rejionno` | Measurements whose pre-fit residual exceeds this are rejected. | number (m) |
| `pos2-rejgdop` | Solutions with a GDOP above this are rejected. | number |
| `pos2-niter` | Filter iterations per epoch. | whole number |
| `pos2-baselen` | Known baseline length to constrain a `movingbase` solution. `0` for no constraint. | number (m) |
| `pos2-basesig` | Uncertainty of the baseline length constraint. | number (m) |

### Solution format (`out-`)

| Option | What to put | Accepted values |
|---|---|---|
| `out-solformat` | Default solution format. In rtkrcv each output has its own `outstrN-format`, which is what actually applies. | `llh`, `xyz`, `enu`, `nmea` |
| `out-outhead` | Write header lines at the top of the solution output. | `off`, `on` |
| `out-outopt` | Also write the processing options into the header. | `off`, `on` |
| `out-outvel` | Add velocity to the solution output. | `off`, `on` |
| `out-timesys` | Time system of the output times. | `gpst`, `utc`, `jst` |
| `out-timeform` | `hms` writes date and time; `tow` writes GPS week and seconds. | `tow`, `hms` |
| `out-timendec` | Decimals of the seconds in output times. | whole number |
| `out-degform` | Latitude/longitude as decimal degrees (`deg`) or degrees-minutes-seconds (`dms`). | `deg`, `dms` |
| `out-fieldsep` | Field separator. Empty for aligned spaces; `,` for CSV. | text |
| `out-outsingle` | `on` outputs the single solution when the differential or PPP solution is unavailable. | `off`, `on` |
| `out-maxsolstd` | Solutions with a standard deviation above this are not output. `0` outputs all. | number (m) |
| `out-height` | `ellipsoidal`: height above the WGS84 ellipsoid. `geodetic`: height above the geoid (sea level). | `ellipsoidal`, `geodetic` |
| `out-geoid` | Geoid model for `geodetic` heights. `internal` needs no file; the others need `file-geoidfile`. | `internal`, `egm96`, `egm08_2.5`, `egm08_1`, `gsi2000` |
| `out-solstatic` | In `static` mode, output every epoch (`all`) or only one final solution (`single`). | `all`, `single` |
| `out-nmeaintv1` | Interval of NMEA RMC and GGA sentences. `0` for every epoch. | number (s) |
| `out-nmeaintv2` | Interval of NMEA GSA and GSV sentences. `0` for every epoch. | number (s) |
| `out-outstat` | Write a solution status file (`rtkrcv_<time>.stat` in the run folder): `state` for filter states, `residual` to add residuals. | `off`, `state`, `residual` |

### Statistics (`stats-`)

Measurement error and filter noise models. The defaults suit most receivers; change them only for tuning.

| Option | What to put | Accepted values |
|---|---|---|
| `stats-eratio1` | Ratio of code error to carrier phase error on L1. Raise it if code measurements are noisy. | number |
| `stats-eratio2` | Same for L2. | number |
| `stats-errphase` | Carrier phase error, constant part. | number (m) |
| `stats-errphaseel` | Carrier phase error, elevation-dependent part. | number (m) |
| `stats-errphasebl` | Carrier phase error, baseline-dependent part. | number (m/10km) |
| `stats-errdoppler` | Doppler measurement error. | number (Hz) |
| `stats-stdbias` | Initial uncertainty of carrier ambiguities. | number (m) |
| `stats-stdiono` | Initial uncertainty of ionosphere delay (per 10 km of baseline). | number (m) |
| `stats-stdtrop` | Initial uncertainty of zenith troposphere delay. | number (m) |
| `stats-prnaccelh` | Process noise of horizontal acceleration (used when `pos1-dynamics` is `on`). | number (m/s^2) |
| `stats-prnaccelv` | Process noise of vertical acceleration. | number (m/s^2) |
| `stats-prnbias` | Process noise of carrier ambiguities. | number (m) |
| `stats-prniono` | Process noise of ionosphere delay. | number (m) |
| `stats-prntrop` | Process noise of troposphere delay. | number (m) |
| `stats-prnpos` | Process noise of position in `static` mode. `0` keeps the position constant. | number (m) |
| `stats-clkstab` | Satellite clock stability. | number (s/s) |

### Rover antenna (`ant1-`)

| Option | What to put | Accepted values |
|---|---|---|
| `ant1-postype` | How the rover position is given. Only used when the rover position is known (`fixed`, `ppp-fixed`). | `llh`, `xyz`, `single`, `posfile`, `rinexhead`, `rtcm`, `raw` |
| `ant1-pos1` | Rover latitude (deg) for `llh`, or ECEF X (m) for `xyz`. | number (deg or m) |
| `ant1-pos2` | Rover longitude (deg) for `llh`, or ECEF Y (m) for `xyz`. | number (deg or m) |
| `ant1-pos3` | Rover height (m) for `llh`, or ECEF Z (m) for `xyz`. | number (m) |
| `ant1-anttype` | Rover antenna model name as written in the antenna file. Empty if unknown. | text |
| `ant1-antdele` | Rover antenna offset from the marker, east. | number (m) |
| `ant1-antdeln` | Rover antenna offset from the marker, north. | number (m) |
| `ant1-antdelu` | Rover antenna offset from the marker, up (the antenna height). | number (m) |

### Base station antenna (`ant2-`)

| Option | What to put | Accepted values |
|---|---|---|
| `ant2-postype` | How the base station position is given. It sets the accuracy of every RTK solution. `rtcm` takes it from the base stream (best choice with a caster); `llh`/`xyz` use the values below; `single` averages the base's own single solutions. | `llh`, `xyz`, `single`, `posfile`, `rinexhead`, `rtcm`, `raw` |
| `ant2-pos1` | Base latitude (deg) for `llh`, or ECEF X (m) for `xyz`. | number (deg or m) |
| `ant2-pos2` | Base longitude (deg) for `llh`, or ECEF Y (m) for `xyz`. | number (deg or m) |
| `ant2-pos3` | Base height (m) for `llh`, or ECEF Z (m) for `xyz`. | number (m) |
| `ant2-anttype` | Base antenna model name as written in the antenna file. Empty if unknown. | text |
| `ant2-antdele` | Base antenna offset from the marker, east. | number (m) |
| `ant2-antdeln` | Base antenna offset from the marker, north. | number (m) |
| `ant2-antdelu` | Base antenna offset from the marker, up. | number (m) |
| `ant2-maxaveep` | Number of epochs to average when `ant2-postype` is `single`. | whole number |
| `ant2-initrst` | `on` restarts that averaging each time the server restarts. | `off`, `on` |

### Files (`file-`)

All optional. Leave empty unless an option above says it needs one.

| Option | What to put | Accepted values |
|---|---|---|
| `file-satantfile` | Satellite antenna file (ANTEX, e.g. `igs14.atx`). Needed for `pos1-posopt1`. | text |
| `file-rcvantfile` | Receiver antenna file (ANTEX). Needed for `pos1-posopt2` and `antN-anttype`. | text |
| `file-staposfile` | Station position file, for `antN-postype` = `posfile`. | text |
| `file-geoidfile` | Geoid data file, for `out-geoid` other than `internal`. | text |
| `file-ionofile` | IONEX file, for `pos1-ionoopt` = `ionex-tec`. | text |
| `file-dcbfile` | Differential code bias file. | text |
| `file-eopfile` | Earth rotation parameter file (PPP). | text |
| `file-blqfile` | Ocean loading (BLQ) file, for `pos1-tidecorr` = `otl`. | text |
| `file-tempdir` | Folder for files downloaded by `ftp`/`http` streams. | text |
| `file-geexefile` | Not used by rtkrcv. | text |
| `file-solstatfile` | Not used by rtkrcv; the status file name is fixed (see `out-outstat`). | text |
| `file-tracefile` | Not used by rtkrcv; start it with `-t <level>` to write `rtkrcv_<time>.trace` in the run folder. | text |
| `file-cmdfile1` | File of commands sent to the rover receiver when the stream opens (e.g. u-blox configuration). | text |
| `file-cmdfile2` | Same for the base station stream. | text |
| `file-cmdfile3` | Same for the correction stream. | text |

### Miscellaneous (`misc-`)

| Option | What to put | Accepted values |
|---|---|---|
| `misc-timeinterp` | Interpolate base station data to the rover epoch (post-processing only). | `off`, `on` |
| `misc-sbasatsel` | SBAS satellite PRN to use. `0` for all. | number |
| `misc-rnxopt1` | Receiver-specific decoder options for the rover stream. Empty unless the receiver's documentation calls for one. | text |
| `misc-rnxopt2` | Receiver-specific decoder options for the base station stream. | text |
| `misc-pppopt` | Extra PPP options. Normally empty. | text |
| `misc-svrcycle` | How often the server processes data. | whole number (ms) |
| `misc-timeout` | A stream with no data for this long is treated as disconnected. | whole number (ms) |
| `misc-reconnect` | Wait before reconnecting a dropped stream. | whole number (ms) |
| `misc-nmeacycle` | How often the NMEA position is sent to the base stream (see `inpstr2-nmeareq`). | whole number (ms) |
| `misc-buffsize` | Input buffer size per stream. | whole number (bytes) |
| `misc-navmsgsel` | Which input's navigation messages (ephemerides) to use. | `all`, `rover`, `base`, `corr` |
| `misc-proxyaddr` | HTTP/NTRIP proxy as `host:port`. Empty for a direct connection. | text |
| `misc-fswapmargin` | Overlap when a time-tagged output file is swapped for the next one. | whole number (s) |
| `misc-startcmd` | Shell command run when the server starts. Empty for none. | text |
| `misc-stopcmd` | Shell command run when the server stops. Empty for none. | text |

### Console (`console-`)

| Option | What to put | Accepted values |
|---|---|---|
| `console-passwd` | Password for the telnet console (`rtkrcv -p <port>`). The web UI logs in with it too. | text |
| `console-timetype` | Time format shown in the console. | `gpst`, `utc`, `jst`, `tow` |
| `console-soltype` | How the `solution` command shows positions. | `dms`, `deg`, `xyz`, `enu`, `pyl` |
| `console-solflag` | Extra columns in the `solution` command, as a sum: `1` standard deviations, `2` age/ratio/satellite count. | sum of `1` std, `2` age/ratio/ns |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `stream` shows the input connected and bytes arriving, but `status` shows `obs(0)` and no solution | `inpstrN-format` does not match the data. NTRIP casters normally send `rtcm3`. |
| The input never connects, or connects and gets no data | Another `rtkrcv` is already using the caster login. `pgrep -l rtkrcv`, then `pkill rtkrcv`. Also check user, password and mountpoint. |
| `output sol1` shows `waiting...` | Normal for `tcpsvr`: nothing has connected to the port yet. |
| An option seems to have no effect | Its name is misspelt (ignored without any message), or its value is not one of the accepted names (`invalid option value` is printed at startup and the default is kept). The web UI flags both. |
| `variable ${NAME} in a stream path is not set` and the server does not start | A stream path uses `${NAME}` but `NAME` is neither in the environment nor in `.env`. Add it to `.env` in the repository root. If you use `rtkrcv` outside the repository, put `.env` beside the options file. |
| No position although data is decoded | Wait a minute or two after the first start: a position needs orbit data for each satellite, which arrives gradually. |
| `undefined reference to clock_gettime` when building on Linux | The makefile links without `-lrt`, which macOS does not have. On Linux with glibc older than 2.17, add `-lrt` to `LDLIBS` in `gcc/makefile`. |

## Changes from RTKLIB 2.4.3 b34

- `src/stream.c`: define the `B460800` and `B921600` serial speeds where the
  system headers lack them (macOS), which stopped the build.
- `gcc/makefile`: link without `-lrt`, which does not exist on macOS.
- `rtkrcv.c`: correct the stream type numbers of the `inpstrN-type`,
  `outstrN-type` and `logstrN-type` options. `ntripcli` was being opened as an
  FTP stream, so NTRIP input never connected.
- `src/rtksvr.c`, `rtkrcv.c`: give the server thread and the console threads a
  16 MB stack. They overflowed the 512 KB default of macOS threads, crashing at
  start and on the `status` command.
- `rtkrcv.c`: starting with `-s` and a `file` output crashed in the overwrite
  check, which assumed a console existed.
- `rtkrcv.c`: `${NAME}` in stream paths is filled in from the environment or
  from a `.env` file in the folder of the options file or a folder above it,
  so logins stay out of the options file.
- `conf/single.conf`, `.env.example`: sample configuration for
  single-point positioning from an NTRIP caster, with solution output to TCP
  port 10009 and to a file.
- `ui/`: the web UI.
