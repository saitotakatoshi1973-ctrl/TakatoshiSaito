module.exports = class MyPlugin {
  async onload() {
    console.log("TakatoshiSaito Plugin loaded");
  }

  onunload() {
    console.log("TakatoshiSaito Plugin unloaded");
  }
};
