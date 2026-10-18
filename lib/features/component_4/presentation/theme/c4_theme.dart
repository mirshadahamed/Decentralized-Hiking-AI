import 'package:flutter/material.dart';

/// Component 4 design system: one colour seed, rounded cards, large touch targets (rangers use the app
/// outdoors, often with gloves) and a consistent spacing scale.
class C4Space {
  static const xs = 4.0, s = 8.0, m = 12.0, l = 16.0, xl = 24.0;
  static const page = EdgeInsets.all(l);
}

class C4Theme {
  static const seed = Color(0xFF2F6B4F); // montane forest green
  static const radius = 16.0;

  static ThemeData of(Brightness brightness) {
    final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: brightness);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius));
    final base = ThemeData(colorScheme: scheme, useMaterial3: true);
    return base.copyWith(
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
        centerTitle: false,
        titleTextStyle: base.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w600, color: scheme.onSurface),
      ),
      cardTheme: CardThemeData(
        shape: shape,
        elevation: 0,
        color: scheme.surfaceContainerLow,
        margin: const EdgeInsets.symmetric(vertical: C4Space.xs),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(minimumSize: const Size(64, 48), shape: shape),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(minimumSize: const Size(64, 48), shape: shape),
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(radius / 2)),
      ),
      chipTheme: base.chipTheme.copyWith(shape: StadiumBorder(side: BorderSide(color: scheme.outlineVariant))),
      listTileTheme: ListTileThemeData(shape: shape),
      navigationBarTheme: NavigationBarThemeData(indicatorColor: scheme.secondaryContainer),
    );
  }
}
