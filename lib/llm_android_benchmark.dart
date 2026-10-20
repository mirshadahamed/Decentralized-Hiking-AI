import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:llama_flutter_android/llama_flutter_android.dart';

const _modelPath =
    '/data/user/0/com.mirshadahamed.decentralized_hiking_ai/files/Qwen3.5-0.8B-Q4_0.gguf';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const LlmAndroidBenchmarkApp());
}

class LlmAndroidBenchmarkApp extends StatelessWidget {
  const LlmAndroidBenchmarkApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Android Local LLM Benchmark',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      home: const _BenchmarkPage(),
    );
  }
}

class _BenchmarkPage extends StatefulWidget {
  const _BenchmarkPage();

  @override
  State<_BenchmarkPage> createState() => _BenchmarkPageState();
}

class _BenchmarkPageState extends State<_BenchmarkPage> {
  LlamaController? _controller;
  bool _isLoading = false;
  bool _isGenerating = false;
  bool _modelLoaded = false;
  String _modelStatus = 'Not loaded';
  String _generationStatus = 'Not started';
  String _loadDuration = '—';
  String _generationDuration = '—';
  String _generatedOutput = '';
  String _gpuDetails = 'Checking is available after pressing Load Qwen Model.';

  @override
  void dispose() {
    final controller = _controller;
    _controller = null;
    if (controller != null) {
      unawaited(controller.dispose());
    }
    super.dispose();
  }

  Future<void> _loadModel() async {
    if (_isLoading || _isGenerating) {
      return;
    }

    setState(() {
      _isLoading = true;
      _modelLoaded = false;
      _modelStatus = 'Loading model…';
      _loadDuration = '—';
      _generationStatus = 'Not started';
      _generationDuration = '—';
      _generatedOutput = '';
    });

    final previousController = _controller;
    _controller = null;
    if (previousController != null) {
      try {
        await previousController.dispose();
      } catch (_) {
        // A failed prior native session should not prevent a fresh benchmark.
      }
    }

    final controller = LlamaController();
    _controller = controller;

    try {
      await _detectGpu(controller);

      final modelFile = File(_modelPath);
      if (!await modelFile.exists()) {
        throw FileSystemException('Model file was not found.', _modelPath);
      }

      final stopwatch = Stopwatch()..start();
      await controller.loadModel(
        modelPath: _modelPath,
        threads: 4,
        contextSize: 1024,
        // This benchmark intentionally starts CPU-only. GPU capability is
        // displayed above but is not forced for the first Android run.
        gpuLayers: 0,
      );
      stopwatch.stop();

      final isLoaded = await controller.isModelLoaded();
      if (!isLoaded) {
        throw StateError('The plugin returned without a loaded model.');
      }

      if (!mounted) {
        return;
      }
      setState(() {
        _modelLoaded = true;
        _modelStatus = 'MODEL LOADED';
        _loadDuration = _formatDuration(stopwatch.elapsed);
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _modelStatus = 'MODEL LOAD FAILED\n$error';
      });
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  Future<void> _detectGpu(LlamaController controller) async {
    try {
      final gpu = await controller.detectGpu();
      if (!mounted) {
        return;
      }
      setState(() {
        _gpuDetails = [
          'Vulkan supported: ${gpu.vulkanSupported}',
          'GPU: ${gpu.gpuName}',
          'Vulkan API version: ${gpu.vulkanApiVersion}',
          'Free RAM: ${_megabytes(gpu.freeRamBytes)}',
          'Recommended GPU layers: ${gpu.recommendedGpuLayers}',
        ].join('\n');
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _gpuDetails = 'GPU/Vulkan detection failed: $error');
    }
  }

  Future<void> _runShortGeneration() async {
    final controller = _controller;
    if (!_modelLoaded || controller == null || _isGenerating || _isLoading) {
      return;
    }

    setState(() {
      _isGenerating = true;
      _generationStatus = 'Generating…';
      _generationDuration = '—';
      _generatedOutput = '';
    });

    final output = StringBuffer();
    final stopwatch = Stopwatch()..start();

    try {
      await for (final token in controller.generate(
        prompt: 'Give three short safety tips for a hiker.',
        maxTokens: 80,
        temperature: 0.2,
        topP: 0.9,
        topK: 40,
      )) {
        output.write(token);
        if (mounted) {
          setState(() => _generatedOutput = output.toString());
        }
      }
      stopwatch.stop();

      if (!mounted) {
        return;
      }
      setState(() {
        _generationStatus = 'GENERATION COMPLETE';
        _generationDuration = _formatDuration(stopwatch.elapsed);
      });
    } catch (error) {
      stopwatch.stop();
      if (!mounted) {
        return;
      }
      setState(() {
        _generationStatus = 'GENERATION FAILED\n$error';
        _generationDuration = _formatDuration(stopwatch.elapsed);
      });
    } finally {
      if (mounted) {
        setState(() => _isGenerating = false);
      }
    }
  }

  String _formatDuration(Duration duration) =>
      '${duration.inMilliseconds} ms (${duration.inSeconds.toStringAsFixed(1)} s)';

  String _megabytes(int bytes) {
    if (bytes < 0) {
      return 'Unknown';
    }
    return '${(bytes / (1024 * 1024)).toStringAsFixed(0)} MB';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Android Local LLM Benchmark')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Qwen3.5-0.8B Android benchmark',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 16),
              _InfoBlock(label: 'Model path', value: _modelPath),
              _InfoBlock(label: 'Model status', value: _modelStatus),
              _InfoBlock(label: 'Load duration', value: _loadDuration),
              _InfoBlock(label: 'GPU / Vulkan', value: _gpuDetails),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: _isLoading || _isGenerating ? null : _loadModel,
                child: Text(_isLoading ? 'Loading…' : 'Load Qwen Model'),
              ),
              const SizedBox(height: 12),
              FilledButton.tonal(
                onPressed: _modelLoaded && !_isGenerating
                    ? _runShortGeneration
                    : null,
                child: Text(
                  _isGenerating ? 'Generating…' : 'Run Short Generation',
                ),
              ),
              const SizedBox(height: 20),
              _InfoBlock(label: 'Generation status', value: _generationStatus),
              _InfoBlock(
                label: 'Generation duration',
                value: _generationDuration,
              ),
              const Text(
                'Generated output',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 6),
              SelectableText(_generatedOutput.isEmpty ? '—' : _generatedOutput),
            ],
          ),
        ),
      ),
    );
  }
}

class _InfoBlock extends StatelessWidget {
  final String label;
  final String value;

  const _InfoBlock({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 3),
          SelectableText(value),
        ],
      ),
    );
  }
}
