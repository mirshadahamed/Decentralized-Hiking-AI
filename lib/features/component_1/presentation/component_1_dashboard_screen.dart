import 'package:flutter/material.dart';
import '../domain/terrain_profile.dart';
import 'component_1_dashboard_controller.dart';

class Component1DashboardScreen extends StatefulWidget {
  const Component1DashboardScreen({
    required this.controller,
    super.key,
  });

  /// This screen owns and disposes the supplied controller.
  final Component1DashboardController controller;

  @override
  State<Component1DashboardScreen> createState() =>
      _Component1DashboardScreenState();
}

class _Component1DashboardScreenState
    extends State<Component1DashboardScreen> {
  @override
  void initState() {
    super.initState();
    widget.controller.start();
  }

  @override
  void dispose() {
    widget.controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Hiking dashboard')),
      body: AnimatedBuilder(
        animation: widget.controller,
        builder: (context, _) {
          final controller = widget.controller;
          final snapshot = controller.snapshot;

          if (snapshot == null && controller.isLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot == null) {
            return _ErrorView(
              message: controller.error?.toString() ??
                  'Terrain data is not available.',
              onRetry: controller.refresh,
            );
          }

          final warning = controller.isHighExertion;
          final color = warning ? Colors.deepOrange : Colors.green;

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (warning)
                Card(
                  color: Colors.deepOrange.withOpacity(0.12),
                  child: const ListTile(
                    leading: Icon(
                      Icons.warning_amber_rounded,
                      color: Colors.deepOrange,
                    ),
                    title: Text('High exertion'),
                    subtitle: Text(
                      'Metabolic cost is above the configured warning level.',
                    ),
                  ),
                ),
              _DataCard(
                title: 'Detected terrain',
                icon: Icons.terrain,
                child: Text(
                  _terrainLabel(snapshot.terrainProfile),
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ),
              _DataCard(
                title: 'Metabolic cost',
                icon: warning ? Icons.warning_amber_rounded : Icons.favorite,
                iconColor: color,
                child: Text(
                  '${snapshot.metabolicCostW.toStringAsFixed(1)} W',
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(color: color),
                ),
              ),
              _DataCard(
                title: 'Offline position',
                icon: Icons.my_location,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Xₜ  ${snapshot.currentX.toStringAsFixed(2)} m'),
                    const SizedBox(height: 6),
                    Text('Yₜ  ${snapshot.currentY.toStringAsFixed(2)} m'),
                    const SizedBox(height: 6),
                    Text(
                      'Heading  ${snapshot.headingRad.toStringAsFixed(2)} rad '
                      '(${(snapshot.headingRad * 180 / 3.141592653589793).toStringAsFixed(1)}°)',
                    ),
                  ],
                ),
              ),
              if (controller.error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    'Latest update failed: ${controller.error}',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }

  String _terrainLabel(TerrainProfile profile) {
    switch (profile) {
      case TerrainProfile.flatGround:
        return 'Flat ground';
      case TerrainProfile.running:
        return 'Running';
      case TerrainProfile.stairs:
        return 'Stairs';
      case TerrainProfile.hikingTrail:
        return 'Hiking trail';
      case TerrainProfile.roughOffTrail:
        return 'Rough off-trail';
    }
  }
}

class _DataCard extends StatelessWidget {
  const _DataCard({
    required this.title,
    required this.icon,
    required this.child,
    this.iconColor,
  });

  final String title;
  final IconData icon;
  final Widget child;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: iconColor),
                const SizedBox(width: 8),
                Text(title, style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({
    required this.message,
    required this.onRetry,
  });

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 40),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: onRetry,
              child: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}
