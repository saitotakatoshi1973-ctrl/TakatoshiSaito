const { Plugin } = require("obsidian");

module.exports = class MyPlugin extends Plugin {
  async onload() {
    console.log("TakatoshiSaito Plugin loaded");
  }

  onunload() {
    console.log("TakatoshiSaito Plugin unloaded");
  }
};
