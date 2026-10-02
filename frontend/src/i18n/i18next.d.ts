import "i18next";

import type { Catalog } from "./en";

// Keys are checked at build time: a key that does not exist is a type error.
declare module "i18next" {
  interface CustomTypeOptions {
    resources: { translation: Catalog };
  }
}
