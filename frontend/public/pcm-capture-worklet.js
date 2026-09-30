// AudioWorklet: forwards mono Float32 input blocks to the main thread, where they are
// downsampled to 16 kHz PCM16 (ADR 0004). No audio is stored or logged here.
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) this.port.postMessage(channel.slice(0));
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
