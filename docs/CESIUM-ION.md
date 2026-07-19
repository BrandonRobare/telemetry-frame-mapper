# Cesium ion publishing

The existing geo-referenced 3D Tiles share bundle can optionally be uploaded to Cesium ion with
`POST /export/reconstructions/{reconstruction_id}/cesium-ion`. It is synchronous: the response
returns the Cesium asset ID after the source ZIP is transferred and ion processing has started.
There is no local queue, stored credential, or background polling.

Enable it only after creating an ion token with `assets:write` (and normally `assets:read` and
`assets:list`) scopes. Keep the token in the named environment variable, never in `config.yaml`:

```yaml
cesium_ion:
  enabled: true
  api_url: "https://api.cesium.com/v1"
  token_env: "CESIUM_ION_TOKEN"
```

The request builds `reconstruction_{id}_share.zip`, creates a `3DTILES` asset, uploads that ZIP
using Cesium's short-lived storage credentials, and notifies ion to begin processing. The API never
returns the configured token or the temporary storage credentials. A disabled integration, absent
token, unsafe URL, invalid Cesium response, or upload failure returns `422` with an actionable
message. Processing continues in Cesium ion; inspect the returned `asset_id` in its dashboard.

See Cesium's [REST upload guide](https://cesium.com/learn/ion/ion-upload-rest/) for token scopes
and the upstream upload lifecycle.
