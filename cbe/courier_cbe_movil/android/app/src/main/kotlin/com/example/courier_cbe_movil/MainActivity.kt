package com.example.courier_cbe_movil

import io.flutter.embedding.android.FlutterActivity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.content.Context
import android.os.Bundle
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import android.content.Intent
import android.os.PowerManager
import android.provider.Settings
import android.net.Uri

class MainActivity: FlutterActivity() {
    private val CHANNEL = "cbe/battery"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createNotificationChannel()
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            if (call.method == "requestIgnoreBatteryOptimizations") {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
                    if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                        try {
                            val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                            intent.data = Uri.parse("package:$packageName")
                            startActivity(intent)
                            result.success(true)
                        } catch (e: Exception) {
                            result.error("ERROR", e.message, null)
                        }
                    } else {
                        result.success(true)
                    }
                } else {
                    result.success(true)
                }
            } else {
                result.notImplemented()
            }
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channelId = "ubicacion_courier_channel"
            val channelName = "Ubicación Courier"
            val importance = NotificationManager.IMPORTANCE_LOW
            val channel = NotificationChannel(channelId, channelName, importance)
            channel.description = "Canal para el servicio de ubicación en segundo plano."

            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }
    }
}
