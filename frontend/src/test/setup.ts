import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup, configure } from '@testing-library/react';

// Poll for deferred React renders on constrained runners without fixed sleeps.
configure({ asyncUtilTimeout: 5000 });
afterEach(cleanup);
// jsdom does not implement the native dialog top layer. Browser QA verifies it.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
}
