import 'package:flutter/material.dart';

abstract final class AppColors {
  static const ink = Color(0xFF18211C);
  static const canvas = Color(0xFFF2F0E9);
  static const acid = Color(0xFFDDF675);
  static const mint = Color(0xFFBCE8D2);
  static const peach = Color(0xFFFFBBA2);
  static const violet = Color(0xFFC8BFF8);
  static const muted = Color(0xFF68736C);
}

abstract final class AppTheme {
  static ThemeData get light {
    final scheme =
        ColorScheme.fromSeed(
          seedColor: AppColors.mint,
          brightness: Brightness.light,
          surface: AppColors.canvas,
        ).copyWith(
          primary: AppColors.ink,
          onPrimary: Colors.white,
          secondary: AppColors.acid,
          onSecondary: AppColors.ink,
        );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.canvas,
      fontFamily: 'SF Pro Display',
      textTheme: Typography.material2021().black.apply(
        bodyColor: AppColors.ink,
        displayColor: AppColors.ink,
        fontFamily: 'SF Pro Display',
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white.withValues(alpha: .54),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 18,
          vertical: 17,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(20),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(20),
          borderSide: BorderSide(color: Colors.white.withValues(alpha: .72)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(20),
          borderSide: const BorderSide(color: AppColors.ink, width: 1.4),
        ),
      ),
    );
  }
}
