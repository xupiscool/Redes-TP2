#-*-coding:utf-8-*-
import sys
import socket
import select
import time
import hashlib
import math
from optparse import OptionParser
from threading import Thread
from threading import Condition
from random import randint

"Classe de recebimento de mensagens"
class Receptor:
	def __init__(self, porta, taxa):
		self.porta = porta
		self.taxa = taxa
		self.sock = self.iniciaServidor()
		self.tamanhoJanela = TAMANHO_JANELA
		self.filaCircular = self.BufferCircular(self.tamanhoJanela)
		self.condition = Condition()
		self.maiorQuadroAceitavel = self.tamanhoJanela
		self.proximoQuadroEsperado = 1
		self.numQuadrosReenviados = 0
		self.recebendo = True
	
	"Classe para implementar janela deslizante"
	class BufferCircular:
		def __init__(self, tamanho):
			self.data = [None for i in xrange(tamanho)]
			self.tamanho = tamanho
		
		"Insere item na última posição, retirando o da primeira"
		def insere(self, x):
			self.data.pop(0)
			self.data.append(x)
		
		"Insere item na posição determinada"
		def inserePosicao(self, posicao, x):
			self.data.pop(posicao)
			self.data.insert(posicao, x)
		
		"Libera espaço retirando item da primeira posição e inserindo None na última posição"
		def liberaEspaco(self):
			self.data.pop(0)
			self.data.insert(self.tamanho - 1, None)
		
		"Verifica se tem espaço livre no buffer"
		def temEspacoLivre(self):
			return self.data[0] == None
		
		"Retorna se o buffer está vazio"
		def bufferEstaVazio(self):
			return self.data[0] == ""
	
		"Retorna o primeiro elemento"
		def primeiro(self):
			return self.data[0]
			
		"Retorna o buffer"
		def get(self):
			return self.data
	
	"Retorna o Buffer do receptor"
	def getBuffer(self):
		return self.filaCircular
	
	"Retorna a condição utilizada pelas threads"
	def getCondition(self):
		return self.condition
	
	"Retorna o socket do receptor"
	def getSock(self):
		return self.sock
	
	"Seta o maior quadro aceitável"
	def setLFA(self, LFA):
		self.maiorQuadroAceitavel = LFA
	
	"Seta o próximo quadro esperado"
	def setNFE(self, NFE):
		self.proximoQuadroEsperado = NFE
	
	"Retorna o maior quadro aceitável"
	def getLFA(self):
		return self.maiorQuadroAceitavel
	
	"Retorna o próximo quadro esperado"
	def getNFE(self):
		return self.proximoQuadroEsperado
	
	"Retorna o tamanho da janela"
	def getTamanhoJanela(self):
		return self.tamanhoJanela
		
	"Retorna a taxa de perda de pacotes passada por parâmetro"
	def getTaxa(self):
		return self.taxa
		
	"Retorna o número de quadros reenviados"
	def getNumQuadrosReenviados(self):
		return self.numQuadrosReenviados
	
	"Incrementa o número de quadros reenviados"
	def setNumQuadrosReenviados(self):
		self.numQuadrosReenviados += 1
	
	"Inicia o servidor"
	def iniciaServidor(self):
		try :
			sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			print "Socket criado"
		except socket.error, msg :
			print "Falha ao criar socket. Código de erro : " + str(msg[0]) + " Mensagem " + msg[1]
			sys.exit()
	
		try:
			sock.bind(("", self.porta))
		except socket.error , msg:
			print "Bind falhou. Código de erro : " + str(msg[0]) + " Message " + msg[1]
			sys.exit()

		print "Servidor iniciado"
	
		return sock
	
	"Envia resposta ao cliente"
	def enviaResposta(self, numQuadro, endereco):
		mensagem = "{0:0>8}".format(numQuadro)
		MD5Mensagem = self.geraMD5Mensagem(mensagem)
		mensagem = MD5Mensagem + mensagem
		self.sock.sendto(mensagem, endereco)
	
	"Gera MD5 para mensagem"
	def geraMD5Mensagem(self, mensagem):
		return hashlib.md5(mensagem).hexdigest()
	
	"Confere MD5 do arquivo recebido e do informado na mensagem inicial"
	def confereMD5(self, arquivo, MD5):
		return str(hashlib.md5(open(arquivo).read()).hexdigest()) == MD5
	
	"Confere MD5 da mensagem recebida com o informado no cabeçalho"
	def confereMD5Mensagem(self, mensagem, MD5):
		return str(hashlib.md5(mensagem).hexdigest()) == MD5
	
	"Seta se está ou não recebendo mensagens"
	def setRecebendo(self, recebimentoAtivo):
		self.recebendo = recebimentoAtivo
	
	"Verifica se está recebendo mensagens"
	def recebimentoAtivo(self):
		return self.recebendo

"Classe para recebimento de mensagens"
class RecebeMensagens(Thread):
	def __init__(self, receptor, saida):
		"Atributos iniciais"
		Thread.__init__(self)
		self.receptor = receptor
		self.condition = receptor.getCondition()
		self.sock = receptor.getSock()
		self.filaCircular = receptor.getBuffer()
		self.LFA = receptor.getLFA()
		self.NFE = receptor.getNFE()
		self.tamanhoJanela = receptor.getTamanhoJanela()
		self.taxa, self.limite = receptor.getTaxa()
		self.saida = saida
		
	def run(self):
		mensagensRecebidas = self.receptor.BufferCircular(2 * self.receptor.getTamanhoJanela())
		mensagemInicial = True
		socket = [self.sock]
		while True:
			self.condition.acquire()
			while True:
				"Caso esteja esperando mensagem inicial"
				if mensagemInicial:
					dados, endereco = self.sock.recvfrom(TAMANHO_PACOTE)
					
					"Recebe o checksum e tipo de transmissão"
					if self.receberMensagem():
						primeiraMensagem = dados
						print "Mensagem inicial recebida"
						MD5Mensagem = dados[:32]
						quadro = int(dados[32:40]) #Não importa
						goBackN = bool(int(dados[40:41]))
						MD5Arquivo = dados[41:]
						
						if not self.receptor.confereMD5Mensagem(dados[32:], MD5Mensagem):
							print "Checksum mensagem não confere"
							continue
						
						"Envia confirmação de transmissão ao cliente"
						self.receptor.enviaResposta(quadro, endereco)
						mensagemInicial = False
					else:
						print "Mensagem não recebida"
						
					continue
				
				"Caso haja mensagens"
				entrada, saida, excecao = select.select(socket, [], [], TIMEOUT)
				if entrada:
					dados, endereco = self.sock.recvfrom(TAMANHO_PACOTE)
					
					"Se mensagem recebida igual mensagem inicial, reenvia confirmação"
					if primeiraMensagem == dados:
						print "Reenviando mensagem inicial não recebida pelo cliente"
						self.receptor.enviaResposta(quadro, endereco)
						continue
					
					if not self.receberMensagem():
						quadro = int(dados[32:40])
						print "Mensagem não recebida", quadro
						continue
					
					quadro = int(dados[32:40])
					checksumMensagem = dados[:32]
					mensagem = dados[40:]
					
					if not self.receptor.confereMD5Mensagem(dados[32:], checksumMensagem):
						print "Checksum mensagem não confere"
						continue
					
					"Caso transmissão não sejaGo Back N"
					if not goBackN:
						"Envia ACK"
						self.receptor.enviaResposta(quadro, endereco)
						
						"Caso já tenha recebido o quadro"
						if quadro < self.NFE or quadro in mensagensRecebidas.get():
							print "Reenviando ACK não recebido pelo cliente: ", quadro
							self.receptor.setNumQuadrosReenviados()
							continue
					
						print "Recebendo quadro", quadro
						print "ACK enviado", quadro
						mensagensRecebidas.insere(quadro)
						
						"Insere dados na devida posição"
						self.filaCircular.inserePosicao(quadro - self.NFE, mensagem)
						
						"Atualiza, próximo quadro esperado"
						while self.NFE in mensagensRecebidas.get():
							self.LFA = self.tamanhoJanela + self.NFE
							self.NFE = self.NFE + 1
#					"Caso seja Go Back N"
					else:
#						"Caso já tenha recebido o quadro"
						if quadro < self.NFE or quadro in mensagensRecebidas.get():
							print "Reenviando ACK não recebido pelo cliente: ", quadro
							self.receptor.setNumQuadrosReenviados()
							self.receptor.enviaResposta(quadro, endereco)
							continue
						
						"Caso quadro seja o esperado envia resposta, caso não, o descarta"
						if quadro == self.NFE:
							self.receptor.enviaResposta(quadro, endereco)
						else:
							print "Quadro não esperado", quadro
							continue
					
						print "Recebendo quadro", quadro
						print "ACK enviado", quadro
						mensagensRecebidas.insere(quadro)
						
						"Insere na posição devida"
						self.filaCircular.inserePosicao(quadro - self.NFE, mensagem)
					
						"Atualiza NFE"
						while self.NFE in mensagensRecebidas.get():
							self.LFA = self.tamanhoJanela + self.NFE
							self.NFE = self.NFE + 1
#				"Caso não receba mensagem, temporização dispara finalizando o programa"
				else:
					print "Expirou timeout, servidor finalizando..."
					self.receptor.setRecebendo(False)
					break
				"Caso buffer esteja cheio, sai do loop"
				if not self.filaCircular.temEspacoLivre():
					break
			
			"Caso o recebimento tenha parado, sai do loop"
			if not self.receptor.recebimentoAtivo():
				break
			
			"Avisa thread de escrita, aguarda ser chamada e libera condição"
			self.condition.notify()
			self.condition.wait()
			self.condition.release()
		
		"Ao fim da transmissão, confere MD5 do arquivo recebido e do checksum recebidos, informa quadros retransmitidos "
		"Finaliza thread"
		if self.receptor.confereMD5(self.saida, MD5Arquivo):
			print "Arquivo recebido corretamente"
		else:
			print "Arquivo recebido com erros"
		print "Quadros reenviados:", self.receptor.getNumQuadrosReenviados()
		self.condition.notify()
		self.condition.release()
		self.sock.close()
	
	"Sorteia se mensagem foi 'perdida ou não'"
	def receberMensagem(self):
		random = randint(1, self.limite)
		return (random > self.taxa)

"Classe de Escrita do Arquivo" 
class EscritaArquivo(Thread):
	def __init__(self, saida, receptor):
		"Atributos iniciais"
		Thread.__init__(self)
		self.saida = saida
		self.receptor = receptor
		self.condition = receptor.getCondition()
		self.filaCircular = receptor.getBuffer()

	def run(self):
		"Limpa ou cria arquivo"
		file = open(self.saida, 'w')
		file.write("")
		file.close()
		while True:
			self.condition.acquire()
			self.condition.notify()
			while True:
				temEspaco = self.filaCircular.temEspacoLivre()
				"Caso buffer contenha informações, as escreve no arquivo, senão sai do loop"
				if temEspaco == False:
					file = open(self.saida, 'a')
					file.write(self.filaCircular.primeiro())
					file.close()	
					self.filaCircular.liberaEspaco()
				else:
					break
			"Espera por notificação da thread de recebimento"
			self.condition.wait()
			
			"Caso o recebimento tenha encerrado, sai do loop, caso não, libera condição"
			if not self.receptor.recebimentoAtivo():
				break
				
			self.condition.release()

"Transforma número em ponto flutuante para inteiro para realizar sorteio"
def taxaInt(taxa):
	limite = 100
	taxaInt = math.floor(taxa)

	while not -0.01 <= taxa - taxaInt <= 0.01:
		taxa *= 10
		limite *= 10
		taxaInt = math.floor(taxa)

	return int(taxaInt), limite

"Faz o recebimento dos parâmetros por linha de comando"
def recebeParametros():	
	usage = "%prog -o Saida -p Porta -t % Perda de pacotes"
	parser = OptionParser(usage=usage)

	parser.add_option("-o", type="string", help="Nome do arquivo de saida", dest="saida")
	parser.add_option("-p", type="int", help="Numero da porta que o servidor esta aguardando conexoes", dest="porta")
	parser.add_option("-t", type="float", help="Especifica a taxa de perda de pacotes em %", dest="taxa")

	(options, args) = parser.parse_args()

	arqSaida = options.saida
	porta = options.porta
	taxa = options.taxa

	# Se faltar algum argumento termina com erro
	if ((arqSaida == None or porta == None or taxa == None)):
		print usage
		print "Erro ao ler argumentos. Todos os argumentos para o programa foram passados?"
		sys.exit()

	print ("Saida : %s " % (options.saida))
	print ("Porta : %s " % (options.porta))
	print ("Taxa : %s " % (options.taxa))
	
	return arqSaida, porta, taxa

"Método principal"
def main():
	arqSaida, porta, taxa = recebeParametros()
	limitesTaxa = taxaInt(taxa)
	receptor = Receptor(porta, limitesTaxa)
	
	threadRecebeMensagens = RecebeMensagens(receptor, arqSaida)
	threadEscritaArquivo = EscritaArquivo(arqSaida, receptor)
    
	threadRecebeMensagens.start()
	threadEscritaArquivo.start()

	threadRecebeMensagens.join()
	threadEscritaArquivo.join()

"Variáveis globais e chamada do método principal"
if __name__ == '__main__':
	TAMANHO_PACOTE = 1500
	TAMANHO_JANELA = 10
	TIMEOUT = 4
	main()
