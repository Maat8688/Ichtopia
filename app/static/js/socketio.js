const socket = io();

socket.on('connect', () => {
    console.log('Connected to server');
    socket.send('Hello, Server!');
});

socket.on('message', (data) => {
    console.log(data);
    const messageElement = document.createElement('div');
    messageElement.textContent = data;
    document.getElementById('messages').appendChild(messageElement);
});