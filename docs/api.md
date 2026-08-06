start a smoke at 250 degrees (or the default setpoint)

    curl -d '{"cmd":"run", "setpoint":250}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

stop the smoke

    curl -d '{"cmd":"stop"}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

current controller state

    curl -X GET http://0.0.0.0:8081/api/stats
