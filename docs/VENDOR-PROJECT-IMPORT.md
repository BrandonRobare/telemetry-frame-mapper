# DroneDeploy and Pix4D project import

This application does **not** import DroneDeploy or Pix4D project packages.
It has no endpoint for `.zip`, `.p4d`, or vendor-exported directory uploads.
The existing `POST /georeferencing/control-points/import` endpoint is only a
WGS84 control-point CSV translator; it neither reads a project nor stores
vendor project state.

## Why there is no package importer

- Pix4Dmapper documents a project as a `.p4d` file plus original image folders
  and a neighboring results directory. Its documented move workflow is
  `Save As`, followed by copying images; it cautions that simply copying files
  can break links. The cited documentation does not define a versioned
  interchange schema for another application to import that project state.
- DroneDeploy documents creating a project, then uploading imagery and optional
  GCP CSVs in its web uploader. The cited public workflow specifies uploads,
  not a versioned project-archive interchange contract.

This sprint found no documented, versioned DroneDeploy or Pix4D interchange
contract suitable for safe implementation. Reading an arbitrary archive or
`.p4d` file would therefore invent vendor compatibility or require a custom
parser to follow untrusted paths. We do neither: no archive extraction means no
zip-slip risk, and no vendor path is read from disk.

## Supported migration path

1. Import the original imagery through the normal browser, server-path, or
   configured watch-folder workflow.
2. If available, use the existing control-point CSV endpoint for the documented
   WGS84 `label,latitude,longitude,elevation_m` interchange only.
3. Export vendor products (for example GeoTIFF, LAS, or other documented
   deliverables) separately; importing those products is intentionally a
   different feature from project import.

## What would unblock a real importer

A future implementation needs all of the following before it accepts an
artifact:

1. A vendor-supported, versioned, portable export contract with a stable schema
   and redistribution permission.
2. Representative, non-sensitive sample packages and expected imported fields.
3. An explicit product decision: import source images and GCPs only, or also
   vendor outputs and processing state.
4. A dedicated staging boundary that allow-lists archive members, rejects path
   traversal, symlinks, oversized entries, and unexpected file counts before
   any extraction.

## Primary vendor references (checked 2026-07-19)

- Pix4D: [move a project between machines](https://support.pix4d.com/hc/en-us/articles/202559229)
  and [project folder structure](https://support.pix4d.com/hc/en-us/articles/202558649).
- DroneDeploy: [project upload workflow](https://help.dronedeploy.com/hc/en-us/articles/1500004963802-Navigating-Projects-in-DroneDeploy)
  and [Smart Uploader](https://help.dronedeploy.com/hc/en-us/articles/7497013045143-Smart-Uploader).
