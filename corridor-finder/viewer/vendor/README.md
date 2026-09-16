# Vendored three.js

Package: `three` v0.169.0, from the public npm registry (https://www.npmjs.com/package/three).
License: MIT — see `THREE-LICENSE` in this directory (copied from the package's `LICENSE` file).
To regenerate `three.module.min.js`, run from `corridor-finder/`:

```
npm pack three@0.169.0 && mkdir -p viewer/vendor && tar xzf three-0.169.0.tgz package/build/three.module.min.js package/LICENSE && cp package/build/three.module.min.js viewer/vendor/three.module.min.js && cp package/LICENSE viewer/vendor/THREE-LICENSE && rm -rf package three-0.169.0.tgz
```
