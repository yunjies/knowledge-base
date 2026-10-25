# DSH Docker deployment contract

The `docker-for-dsh` project repository owns the image build, GitHub Actions workflow, Unraid template, and current installation steps. Use its [README](../../projects/docker-for-dsh/README.md) and [Unraid template](../../projects/docker-for-dsh/unraid/dsh.xml) as the deployment source of truth.

## Container boundary

- DSH runs as a standalone container and does not require a TTSwitch container to start.
- When a TTSwitch service is available on the shared private network, configure its private endpoint in the DSH profile; keep its route-specific path in private appdata.
- The public image and template contain no TTSwitch route identifier, credential file, launch token, or user-specific proxy URL.

## Persistent state and version selection

- Keep `/data` and `/workspace` on persistent Unraid appdata mounts; the template supplies the default host paths.
- Preserve the existing `/data/.dsh` profile when updating the image so that the Codex subscription plugin, credentials, and user configuration remain available.
- `DSH_VERSION` defaults to `latest`; on each start the launcher resolves the selected NPM tag or version and installs DSH only when the installed version differs.
- The first start of a fresh data directory requires access to the NPM registry. If the registry is unavailable and no DSH version is already installed, startup fails rather than selecting an unknown release.
- The image installs `dsh-codex-subscription` into the web profile. Other plugin build scripts remain governed by the profile's pnpm `allowBuilds` policy and require package-specific review.

## Network and proxy integration

- Attach DSH and TTSwitch to the same trusted private Docker network when model requests should use Docker DNS.
- If a token registrar is configured, its source-IP policy must include the DSH container address selected by the Unraid template.
- Set `DSH_PUBLIC_URL` and `DSH_TRUSTED_HOST` to the externally reachable DSH Web authority.
- Set `DSH_TOKEN_REGISTER_URL` only to an explicitly trusted registrar; when unset, launch-token registration is disabled.

## Verification

Verify the GHCR image is anonymously pullable before installing the template; a public source repository alone does not make its container package public. Use the Docker template to update the DSH container while preserving its persistent `/data` and `/workspace` mounts.

After deployment, inspect the running container's image and mounts, read `dsh --version`, and confirm `dsh-codex-subscription` is present in the persistent web profile. Verify DSH Web through the configured reverse proxy. If token registration is enabled, confirm the registrar reports success without exposing the token. Test TTSwitch model calls only when a TTSwitch provider has been configured.

## Security boundary

The container runs as root inside Docker but is not privileged and must not receive the Docker socket or host-root mounts. Packages installed with `apt` at runtime modify the writable container layer and are lost when that container is recreated; persistent user data belongs in `/data` and `/workspace`.
