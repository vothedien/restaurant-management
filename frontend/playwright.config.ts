import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./e2e',fullyParallel:false,workers:1,timeout:60000,use:{baseURL:'http://localhost:5174',channel:'chrome',headless:true,trace:'retain-on-failure',screenshot:'only-on-failure'},outputDir:'../tmp/inventory-playwright',reporter:'list'});
